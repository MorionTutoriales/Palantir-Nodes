"""Utilidades compartidas por los nodos de OpenCV (sin Qt)."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def image_in(value: Any, label: str = "imagen") -> np.ndarray:
    """Valida una imagen de entrada y la devuelve como uint8 de 2 o 3-4 dimensiones."""
    if not isinstance(value, np.ndarray):
        raise ValueError(f"La entrada '{label}' no es una imagen válida")
    if value.ndim not in (2, 3) or value.size == 0:
        raise ValueError(f"La entrada '{label}' está vacía o tiene un formato inesperado")
    if value.ndim == 3:
        if value.shape[2] == 1:
            value = value[:, :, 0]
        elif value.shape[2] not in (3, 4):
            raise ValueError(
                f"La entrada '{label}' tiene {value.shape[2]} canales (se esperan 1, 3 o 4)"
            )
    return to_uint8(value)


def to_uint8(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img
    if img.dtype == np.uint16:
        return (img >> 8).astype(np.uint8)
    if np.issubdtype(img.dtype, np.floating):
        return np.clip(np.rint(img * 255.0), 0, 255).astype(np.uint8)
    return np.clip(img, 0, 255).astype(np.uint8)


def as_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    code = cv2.COLOR_BGRA2GRAY if img.shape[2] == 4 else cv2.COLOR_BGR2GRAY
    return cv2.cvtColor(img, code)


def as_bgr(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


def match(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Iguala tamaño (al de ``a``) y canales de dos imágenes para operar entre ellas."""
    if b.shape[:2] != a.shape[:2]:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    if a.ndim == 2 and b.ndim == 2:
        return a, b
    return as_bgr(a), as_bgr(b)


def odd(value: float, minimum: int = 1) -> int:
    k = max(minimum, int(value))
    return k if k % 2 else k + 1


def rgb_to_bgr(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return (int(color[2]), int(color[1]), int(color[0]))


INTERPOLATION = {
    "linear": cv2.INTER_LINEAR,
    "nearest": cv2.INTER_NEAREST,
    "cubic": cv2.INTER_CUBIC,
    "area": cv2.INTER_AREA,
    "lanczos": cv2.INTER_LANCZOS4,
}

KERNEL_SHAPES = {
    "rect": cv2.MORPH_RECT,
    "ellipse": cv2.MORPH_ELLIPSE,
    "cross": cv2.MORPH_CROSS,
}
