"""Conversión entre el texto/gestos del usuario y los valores de los campos de un nodo.

Funciones puras (sin Qt) para poder probarlas aisladas.
"""

from __future__ import annotations

import math
import re
from typing import Any

from palantir_nodes.nodes.specs import ParamKind, ParamSpec

NUMERIC_KINDS = (ParamKind.INT, ParamKind.FLOAT)
VECTOR_KINDS = (ParamKind.VECTOR2, ParamKind.VECTOR3)
# Tipos que se editan escribiendo texto (el resto usa menú, casilla o diálogo).
TEXT_KINDS = (*NUMERIC_KINDS, *VECTOR_KINDS, ParamKind.STRING)

_FINE_FACTOR = 0.1
_INT_UNITS_PER_PIXEL = 1 / 6  # al menos 6 px por unidad
_SPAN_PIXELS = 400.0  # arrastrar 400 px recorre todo el rango (si lo tiene)


def _number(text: str) -> float:
    cleaned = text.strip().replace(",", ".")
    if not cleaned:
        raise ValueError("Escribe un número")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(f"'{text.strip()}' no es un número") from None
    if not math.isfinite(value):
        raise ValueError("El número debe ser finito")
    return value


def format_field_text(spec: ParamSpec, value: Any) -> str:
    """Texto con el que se abre el editor en línea."""
    if spec.kind is ParamKind.INT:
        return str(int(value))
    if spec.kind is ParamKind.FLOAT:
        return format(float(value), ".6g")
    if spec.kind in VECTOR_KINDS:
        return ", ".join(format(float(c), ".6g") for c in value)
    return str(value)


def parse_field_text(spec: ParamSpec, text: str) -> Any:
    """Interpreta el texto escrito. Lanza ``ValueError`` con un mensaje legible.

    El resultado aún debe pasar por ``spec.coerce`` (que recorta al rango válido).
    """
    if spec.kind is ParamKind.INT:
        return int(round(_number(text)))
    if spec.kind is ParamKind.FLOAT:
        return _number(text)
    if spec.kind is ParamKind.STRING:
        return text
    if spec.kind in VECTOR_KINDS:
        size = 2 if spec.kind is ParamKind.VECTOR2 else 3
        parts = [p for p in re.split(r"[;,\s]+", text.strip()) if p]
        if len(parts) != size:
            raise ValueError(f"Escribe {size} valores separados por comas (ej.: 1, 2, 3)")
        return tuple(_number(p) for p in parts)
    raise ValueError("Este campo no se edita como texto")


def scrub_value(spec: ParamSpec, start: Any, dx_pixels: float, *, fine: bool = False) -> Any:
    """Valor resultante de arrastrar ``dx_pixels`` horizontalmente desde ``start``."""
    factor = _FINE_FACTOR if fine else 1.0
    low, high = spec.minimum, spec.maximum
    span = (high - low) if low is not None and high is not None else None
    if spec.kind is ParamKind.INT:
        per_pixel = max(span / _SPAN_PIXELS, _INT_UNITS_PER_PIXEL) if span else _INT_UNITS_PER_PIXEL
        return int(round(start + dx_pixels * per_pixel * factor))
    if span:
        per_pixel = span / _SPAN_PIXELS
    else:
        per_pixel = max(abs(float(start)) * 0.01, 0.01)
    return round(float(start) + dx_pixels * per_pixel * factor, spec.decimals)
