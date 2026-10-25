"""Detección con MediaPipe (se copia tal cual al script exportado).

Usa la API «Tasks» de MediaPipe, que necesita un archivo de modelo por detector. Si no se
indica uno, se descarga el modelo oficial la primera vez y se guarda en
``~/.palantir_nodes/models`` (o en la carpeta de la variable ``PALANTIR_NODES_MODELS``).
El paquete ``mediapipe`` se importa al crear el detector, no al cargar este módulo.

Los resultados son datos de Python simples: una lista con un diccionario por cada mano,
persona o rostro, con ``points`` (lista de ``(x, y)`` en píxeles), ``box`` (``(x, y, ancho,
alto)``) y ``score``.
"""

from __future__ import annotations

import os
import sys
import urllib.request

import cv2
import numpy as np

from palantir_nodes.nodes.library._cv import as_bgr

_BASE = "https://storage.googleapis.com/mediapipe-models/"

# tipo -> (nombre del archivo, dirección de descarga del modelo oficial)
MP_MODELS = {
    "hands": (
        "hand_landmarker.task",
        _BASE + "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    ),
    "pose": (
        "pose_landmarker_lite.task",
        _BASE + "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    ),
    "face_mesh": (
        "face_landmarker.task",
        _BASE + "face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    ),
    "face_detection": (
        "blaze_face_short_range.tflite",
        _BASE + "face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
    ),
}

# Uniones entre puntos que se dibujan (los 21 puntos de la mano y los 33 del cuerpo).
MP_HAND_LINES = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
    (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
    (17, 18), (18, 19), (19, 20),
]  # fmt: skip
MP_POSE_LINES = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10), (11, 12),
    (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19), (12, 14), (14, 16),
    (16, 18), (16, 20), (16, 22), (18, 20), (11, 23), (12, 24), (23, 24), (23, 25),
    (24, 26), (25, 27), (26, 28), (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
]  # fmt: skip


def mp_models_dir():
    base = os.environ.get("PALANTIR_NODES_MODELS")
    return base or os.path.join(os.path.expanduser("~"), ".palantir_nodes", "models")


def mp_model_path(kind, custom=""):
    """Ruta del modelo: el indicado por el usuario o el oficial (se descarga la primera vez)."""
    if custom:
        if not os.path.isfile(custom):
            raise ValueError(f"No existe el modelo: {custom}")
        return custom
    name, url = MP_MODELS[kind]
    path = os.path.join(mp_models_dir(), name)
    if os.path.isfile(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        urllib.request.urlretrieve(url, path + ".part")
        os.replace(path + ".part", path)
    except Exception as exc:
        if os.path.exists(path + ".part"):
            os.remove(path + ".part")
        raise ValueError(
            f"No se pudo descargar el modelo de MediaPipe ({exc}). "
            f"Descárgalo de {url} y elígelo en «Modelo»."
        ) from None
    return path


def mp_create(kind, options, model_path):
    """Crea el detector de ``kind`` (``options``: tuplas ``(nombre, valor)``)."""
    try:
        from mediapipe.tasks import python as tasks
        from mediapipe.tasks.python import vision
    except ImportError as exc:
        raise ValueError(
            f"No se pudo cargar 'mediapipe' ({exc}). Instálalo en el Python que ejecuta esto: "
            f'"{sys.executable}" -m pip install mediapipe'
        ) from None
    opts = dict(options)
    base = tasks.BaseOptions(model_asset_path=model_path)
    mode = vision.RunningMode.IMAGE
    confidence = opts.get("confidence", 0.5)
    count = opts.get("max", 1)
    if kind == "hands":
        return vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=base,
                running_mode=mode,
                num_hands=count,
                min_hand_detection_confidence=confidence,
            )
        )
    if kind == "pose":
        return vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=base,
                running_mode=mode,
                num_poses=count,
                min_pose_detection_confidence=confidence,
            )
        )
    if kind == "face_mesh":
        return vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=base,
                running_mode=mode,
                num_faces=count,
                min_face_detection_confidence=confidence,
            )
        )
    return vision.FaceDetector.create_from_options(
        vision.FaceDetectorOptions(
            base_options=base, running_mode=mode, min_detection_confidence=confidence
        )
    )


def mp_detector(store, name, kind, options, custom_model=""):
    """Detector reutilizable: se crea una vez y se vuelve a crear si cambian las opciones.

    ``store`` guarda ``nombre -> (clave, detector, función_de_cierre)``.
    """
    key = (kind, options, custom_model)
    entry = store.get(name)
    if entry is not None and entry[0] == key:
        return entry[1]
    if entry is not None:
        entry[2]()
    detector = mp_create(kind, options, mp_model_path(kind, custom_model))
    store[name] = (key, detector, detector.close)
    return detector


def mp_close_all(store):
    for entry in list(store.values()):
        try:
            entry[2]()
        except Exception:
            pass
    store.clear()


def mp_detect(detector, kind, image):
    """Detecciones en ``image`` (BGR o gris), como lista de diccionarios simples."""
    import mediapipe as mp

    frame = image if image.ndim == 3 and image.shape[2] == 3 else as_bgr(image)
    rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    height, width = rgb.shape[:2]
    found = []
    if kind == "face_detection":
        for item in result.detections:
            box = item.bounding_box
            found.append(
                {
                    "points": [(k.x * width, k.y * height) for k in item.keypoints],
                    "box": (box.origin_x, box.origin_y, box.width, box.height),
                    "score": float(item.categories[0].score) if item.categories else 0.0,
                }
            )
        return found
    attribute = {"hands": "hand_landmarks", "pose": "pose_landmarks", "face_mesh": "face_landmarks"}
    groups = getattr(result, attribute[kind])
    for group in groups:
        points = [(p.x * width, p.y * height) for p in group]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)) if points else (0, 0, 0, 0)
        found.append({"points": points, "box": box, "score": 1.0})
    return found


def mp_draw(image, kind, detections, color=(0, 255, 0)):
    """Copia de ``image`` con los puntos, uniones y cajas dibujados (``color`` es RGB)."""
    out = (image if image.ndim == 3 and image.shape[2] == 3 else as_bgr(image)).copy()
    bgr = (int(color[2]), int(color[1]), int(color[0]))
    lines = {"hands": MP_HAND_LINES, "pose": MP_POSE_LINES}.get(kind, [])
    radius = 1 if kind == "face_mesh" else 3
    for item in detections:
        points = [(int(round(x)), int(round(y))) for x, y in item["points"]]
        for a, b in lines:
            if a < len(points) and b < len(points):
                cv2.line(out, points[a], points[b], bgr, 2)
        for point in points:
            cv2.circle(out, point, radius, bgr, -1)
        if kind == "face_detection":
            x, y, w, h = item["box"]
            cv2.rectangle(out, (int(x), int(y)), (int(x + w), int(y + h)), bgr, 2)
    return out


def pick_landmark(landmarks, subject, index):
    """Punto ``index`` de la mano/persona/rostro ``subject``: ``(x, y, encontrado)``."""
    if 0 <= subject < len(landmarks) and 0 <= index < len(landmarks[subject]):
        x, y = landmarks[subject][index]
        return float(x), float(y), True
    return 0.0, 0.0, False
