"""Apertura y lectura de video y cámaras.

Las cuatro funciones ``open_*`` / ``read_frame`` se copian tal cual al script exportado
(ver ``codegen/helpers.py``), de modo que el motor y el script usan el mismo código.
"""

from __future__ import annotations

import os
import sys

import cv2
import numpy as np


def open_video_capture(path: str) -> cv2.VideoCapture:
    """Abre un archivo de video o lanza ``ValueError`` explicativo."""
    if not path:
        raise ValueError("No se ha seleccionado ningún archivo de video")
    if not os.path.isfile(path):
        raise ValueError(f"No existe el archivo: {path}")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise ValueError(f"No se pudo abrir el video: {os.path.basename(path)}")
    return cap


def open_camera_capture(index: int) -> cv2.VideoCapture:
    """Abre una cámara o lanza ``ValueError`` explicativo."""
    if sys.platform == "win32":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        raise ValueError(f"No se pudo abrir la cámara {index} (¿está en uso o desconectada?)")
    return cap


def read_frame(cap: cv2.VideoCapture, loop: bool = False) -> np.ndarray | None:
    """Siguiente fotograma, o ``None`` si el video terminó (reinicia si ``loop``)."""
    ok, frame = cap.read()
    if not ok and loop:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
    return frame if ok else None


def open_video_writer(path: str, fps: float, codec: str, frame: np.ndarray) -> cv2.VideoWriter:
    """Crea un VideoWriter con el tamaño de ``frame`` o lanza ``ValueError``."""
    if not path:
        raise ValueError("No se ha indicado el archivo de video de destino")
    height, width = frame.shape[:2]
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*codec), fps, (width, height))
    if not writer.isOpened():
        writer.release()
        raise ValueError(f"No se pudo crear el video '{path}' con el códec {codec}")
    return writer


class CaptureSource:
    """Fuente de fotogramas sobre un ``cv2.VideoCapture``."""

    def __init__(self, cap: cv2.VideoCapture, *, loop: bool = False, paced: bool = False) -> None:
        self._cap = cap
        self.loop = loop
        fps = cap.get(cv2.CAP_PROP_FPS)
        # Los archivos se reproducen a su velocidad; las cámaras ya imponen la suya.
        self.fps: float | None = fps if paced and fps and fps > 0 else None

    def read(self) -> np.ndarray | None:
        return read_frame(self._cap, self.loop)

    def release(self) -> None:
        self._cap.release()

    @property
    def is_open(self) -> bool:
        return self._cap.isOpened()
