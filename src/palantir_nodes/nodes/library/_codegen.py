"""Ayudas de generación de código para parámetros que pueden llegar como ``Expr``.

Cuando un parámetro numérico se conecta a otro nodo su valor solo se conoce al ejecutar el
script, así que las operaciones que normalmente se resolvían al generar (volver impar un
kernel, p. ej.) pasan a generarse como código.
"""

from __future__ import annotations

from typing import Any

from palantir_nodes.nodes.base import Expr
from palantir_nodes.nodes.library._cv import odd


def odd_expr(gen: Any, value: Any, minimum: int = 1) -> tuple[str, list[str]]:
    """Expresión y líneas previas para ``odd(value, minimum)`` (ver ``_cv.odd``)."""
    if isinstance(value, Expr):
        gen.helper("odd")
        var = gen.new_var("odd_size")
        return var, [f"{var} = odd({value}, {minimum})"]
    return str(odd(value, minimum)), []


def positive_int_expr(gen: Any, value: Any) -> tuple[str, list[str]]:
    """Expresión y líneas previas para ``max(1, int(value))``."""
    if isinstance(value, Expr):
        var = gen.new_var("size")
        return var, [f"{var} = max(1, int({value}))"]
    return str(max(1, int(value))), []
