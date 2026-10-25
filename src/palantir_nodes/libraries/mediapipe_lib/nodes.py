"""Nodos de MediaPipe. No se registran solos: los añade el gestor de librerías."""

from __future__ import annotations

from typing import Any

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.libraries.mediapipe_lib import runtime
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import register_category
from palantir_nodes.nodes.library._cv import image_in
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec

MEDIAPIPE = "MediaPipe"
register_category(MEDIAPIPE, "#2F6B8F", 36)

_DRAW = ParamSpec(
    "draw",
    ParamKind.BOOL,
    True,
    label="Dibujar",
    connectable=False,
    tooltip="Dibuja los puntos y uniones sobre la imagen de salida (si no, sale sin cambios)",
)
_MODEL = ParamSpec(
    "model",
    ParamKind.FILE_PATH,
    "",
    label="Modelo",
    file_filter="Modelo de MediaPipe (*.task *.tflite);;Todos (*)",
    tooltip=(
        "Archivo de modelo. Vacío: se descarga el modelo oficial la primera vez "
        "(necesita conexión a Internet) y se guarda en ~/.palantir_nodes/models."
    ),
)


def _confidence(default: float = 0.5) -> ParamSpec:
    return ParamSpec(
        "confidence",
        ParamKind.FLOAT,
        default,
        label="Confianza mínima",
        minimum=0.0,
        maximum=1.0,
        connectable=False,
    )


def _count(label: str, default: int, maximum: int) -> ParamSpec:
    return ParamSpec(
        "max", ParamKind.INT, default, label=label, minimum=1, maximum=maximum, connectable=False
    )


class MediaPipeNode(NodeDefinition):
    """Detector de MediaPipe sobre una imagen: dibuja y entrega los puntos encontrados."""

    category = MEDIAPIPE
    kind = ""
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (
        OutputSpec("image", T.IMAGE, "Imagen"),
        OutputSpec("count", T.INTEGER, "Cantidad"),
        OutputSpec("landmarks", T.ANY, "Puntos"),
        OutputSpec("boxes", T.ANY, "Cajas"),
    )

    @classmethod
    def options(cls, params: dict[str, Any]) -> tuple:
        values = [("confidence", float(params["confidence"]))]
        if "max" in params:
            values.insert(0, ("max", int(params["max"])))
        return tuple(values)

    def process(self, ctx, inputs, params):
        image = image_in(inputs["image"])
        detector = runtime.mp_detector(
            ctx.resources, ctx.node_id, self.kind, self.options(params), params["model"]
        )
        found = runtime.mp_detect(detector, self.kind, image)
        out = runtime.mp_draw(image, self.kind, found) if params["draw"] else image
        return {
            "image": out,
            "count": len(found),
            "landmarks": [item["points"] for item in found],
            "boxes": [item["box"] for item in found],
        }

    def generate_code(self, gen, inputs, params):
        for name in ("mp_detector", "mp_detect", "mp_draw", "mp_close_all"):
            gen.helper(name)
        gen.add_import("import urllib.request")
        gen.add_requirement("mediapipe")
        gen.add_prelude("_MP_STORE = {}")
        detector, found, out = gen.new_var("detector"), gen.new_var("found"), gen.new_var("marked")
        image = inputs["image"]
        lines = [
            f"{detector} = mp_detector(_MP_STORE, {detector!r}, {self.kind!r}, "
            f"{self.options(params)!r}, {params['model']!r})",
            f"{found} = mp_detect({detector}, {self.kind!r}, {image})",
        ]
        if params["draw"]:
            lines.append(f"{out} = mp_draw({image}, {self.kind!r}, {found})")
        else:
            lines.append(f"{out} = {image}")
        return CodeFragment(
            lines,
            {
                "image": out,
                "count": f"len({found})",
                "landmarks": f"[item['points'] for item in {found}]",
                "boxes": f"[item['box'] for item in {found}]",
            },
            cleanup=["mp_close_all(_MP_STORE)"],
        )


class HandLandmarks(MediaPipeNode):
    type_id = "mp.hands"
    label = "Hand Landmarks"
    description = (
        "Detecta manos y sus 21 puntos (punta del índice = 8, del pulgar = 4). «Puntos» da, "
        "por cada mano, la lista de puntos en píxeles; úsala con «Landmark Point»."
    )
    kind = "hands"
    params = (_count("Manos", 2, 10), _confidence(), _DRAW, _MODEL)


class PoseLandmarks(MediaPipeNode):
    type_id = "mp.pose"
    label = "Pose Landmarks"
    description = (
        "Detecta el cuerpo y sus 33 puntos (0 = nariz, 11/12 = hombros, 15/16 = muñecas, "
        "27/28 = tobillos). «Puntos» da, por cada persona, la lista de puntos en píxeles."
    )
    kind = "pose"
    params = (_count("Personas", 1, 5), _confidence(), _DRAW, _MODEL)


class FaceMesh(MediaPipeNode):
    type_id = "mp.face_mesh"
    label = "Face Mesh"
    description = (
        "Detecta rostros y su malla de 478 puntos. «Puntos» da, por cada rostro, la lista de "
        "puntos en píxeles."
    )
    kind = "face_mesh"
    params = (_count("Rostros", 1, 5), _confidence(), _DRAW, _MODEL)


class FaceDetection(MediaPipeNode):
    type_id = "mp.face_detection"
    label = "Face Detection"
    description = (
        "Detecta rostros: «Cajas» da (x, y, ancho, alto) de cada uno y «Puntos» sus 6 puntos "
        "clave (ojos, nariz, boca y orejas). Es más rápido que Face Mesh."
    )
    kind = "face_detection"
    params = (_confidence(), _DRAW, _MODEL)


class LandmarkPoint(NodeDefinition):
    type_id = "mp.landmark_point"
    label = "Landmark Point"
    category = MEDIAPIPE
    description = (
        "Toma un punto de la salida «Puntos» de un detector: «Elemento» es cuál mano, persona o "
        "rostro (0 = el primero) e «Índice» cuál punto. Da sus coordenadas en píxeles y si existe."
    )
    inputs = (InputSpec("landmarks", T.ANY, "Puntos"),)
    outputs = (
        OutputSpec("point", T.VECTOR2, "Punto"),
        OutputSpec("x", T.FLOAT, "X"),
        OutputSpec("y", T.FLOAT, "Y"),
        OutputSpec("found", T.BOOLEAN, "Encontrado"),
    )
    params = (
        ParamSpec(
            "subject",
            ParamKind.INT,
            0,
            label="Elemento",
            minimum=0,
            maximum=20,
            connectable=False,
        ),
        ParamSpec(
            "index",
            ParamKind.INT,
            8,
            label="Índice",
            minimum=0,
            maximum=1000,
            connectable=False,
            tooltip="Mano: 0-20 (8 = punta del índice). Cuerpo: 0-32. Malla de rostro: 0-477.",
        ),
    )

    def process(self, ctx, inputs, params):
        landmarks = inputs["landmarks"] or []
        x, y, found = runtime.pick_landmark(landmarks, params["subject"], params["index"])
        return {"point": (x, y), "x": x, "y": y, "found": found}

    def generate_code(self, gen, inputs, params):
        gen.helper("pick_landmark")
        x, y, found, point = (gen.new_var(n) for n in ("point_x", "point_y", "found", "point"))
        lines = [
            f"{x}, {y}, {found} = pick_landmark({inputs['landmarks']} or [], "
            f"{params['subject']!r}, {params['index']!r})",
            f"{point} = ({x}, {y})",
        ]
        return CodeFragment(lines, {"point": point, "x": x, "y": y, "found": found})
