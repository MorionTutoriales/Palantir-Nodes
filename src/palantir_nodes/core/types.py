"""Tipos de socket, sus colores y las conversiones implícitas permitidas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SocketType(Enum):
    IMAGE = "Image"
    VIDEO = "Video"
    FLOAT = "Float"
    INTEGER = "Integer"
    BOOLEAN = "Boolean"
    STRING = "String"
    COLOR = "Color"
    VECTOR2 = "Vector2"
    VECTOR3 = "Vector3"
    ANY = "Any"

    @property
    def color(self) -> str:
        return SOCKET_COLORS[self]


SOCKET_COLORS: dict[SocketType, str] = {
    SocketType.IMAGE: "#E3C53C",
    SocketType.VIDEO: "#E5822E",
    SocketType.FLOAT: "#A1A1A1",
    SocketType.INTEGER: "#4D9E5A",
    SocketType.BOOLEAN: "#CCA6D6",
    SocketType.STRING: "#5FA9E8",
    SocketType.COLOR: "#D9604F",
    SocketType.VECTOR2: "#8C80E6",
    SocketType.VECTOR3: "#6363C7",
    SocketType.ANY: "#3FBFA0",
}


@dataclass(frozen=True)
class Conversion:
    """Conversión implícita entre dos tipos de socket."""

    description: str
    convert: Callable[[Any], Any]


# Únicas conversiones implícitas permitidas: (origen, destino) -> conversión.
IMPLICIT_CONVERSIONS: dict[tuple[SocketType, SocketType], Conversion] = {
    (SocketType.INTEGER, SocketType.FLOAT): Conversion("Integer → Float", float),
    (SocketType.FLOAT, SocketType.INTEGER): Conversion(
        "Float → Integer (redondeo)", lambda v: int(round(v))
    ),
    (SocketType.BOOLEAN, SocketType.INTEGER): Conversion("Boolean → Integer", int),
    (SocketType.BOOLEAN, SocketType.FLOAT): Conversion("Boolean → Float", float),
    (SocketType.COLOR, SocketType.VECTOR3): Conversion(
        "Color → Vector3", lambda v: tuple(float(c) for c in v)
    ),
    (SocketType.VECTOR3, SocketType.COLOR): Conversion(
        "Vector3 → Color", lambda v: tuple(max(0, min(255, int(round(c)))) for c in v)
    ),
}


def is_compatible(src: SocketType, dst: SocketType) -> bool:
    """Indica si una salida de tipo ``src`` puede conectarse a una entrada ``dst``.

    ``Any`` es un tipo genérico controlado: una entrada ``Any`` acepta cualquier tipo,
    pero una salida ``Any`` solo puede conectarse a entradas ``Any``.
    """
    if src is dst or dst is SocketType.ANY:
        return True
    return (src, dst) in IMPLICIT_CONVERSIONS


def conversion_between(src: SocketType, dst: SocketType) -> Conversion | None:
    """Conversión necesaria para pasar de ``src`` a ``dst``, o ``None`` si no hace falta."""
    if src is dst or dst is SocketType.ANY:
        return None
    return IMPLICIT_CONVERSIONS.get((src, dst))
