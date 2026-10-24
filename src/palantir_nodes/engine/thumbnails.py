"""Miniaturas para la previsualización dentro de los nodos. No depende de Qt."""

from __future__ import annotations

import cv2
import numpy as np

# Tamaño máximo de una miniatura (ancho, alto) en píxeles. Es mayor que el área que ocupa
# en el nodo para que se vea nítida al acercar el zoom.
PREVIEW_MAX = (256, 160)


def make_thumbnail(img: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    """Reduce ``img`` para que quepa en ``max_width`` × ``max_height`` conservando la
    proporción. Nunca amplía. Devuelve una copia independiente de la imagen original."""
    height, width = img.shape[:2]
    scale = min(max_width / width, max_height / height, 1.0)
    if scale < 1.0:
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        return np.ascontiguousarray(cv2.resize(img, size, interpolation=cv2.INTER_AREA))
    return np.array(img)  # copia: la original puede estar en la caché del ejecutor
