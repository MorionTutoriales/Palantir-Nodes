"""Ejecución del código de un nodo personalizado.

``coerce_results`` se copia tal cual al script exportado, de modo que la aplicación y el
script normalizan las salidas con el mismo código. Debe ser una única función que solo
dependa de ``np``.
"""

from __future__ import annotations

import builtins
import math
import textwrap
import traceback
import typing
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np

FACTORY_NAME = "_make_node"


class CustomNodeError(RuntimeError):
    """Fallo al ejecutar el código de un nodo personalizado (el mensaje ya es legible)."""


def factory_source(code: str, function_name: str) -> str:
    """Código del nodo envuelto en una función fábrica.

    Así sus funciones auxiliares y variables quedan aisladas de las de otros nodos y del
    resto del script. La línea 1 es ``def``: la línea N del usuario es la N + 1 de este texto.
    """
    body = textwrap.indent(code.rstrip("\n"), "    ") if code.strip() else "    pass"
    return f"def {FACTORY_NAME}():\n{body}\n    return {function_name}\n"


def build_namespace() -> dict[str, Any]:
    """Nombres disponibles para el código del usuario sin importarlos."""
    return {
        "__builtins__": builtins,
        "np": np,
        "cv2": cv2,
        "math": math,
        "Any": typing.Any,
        "Literal": typing.Literal,
        "Image": np.ndarray,
        "Color": tuple,
        "Vector2": tuple,
        "Vector3": tuple,
    }


def filename_for(label: str) -> str:
    return f"<nodo:{label}>"


def compile_node_function(code: str, function_name: str, label: str) -> Callable[..., Any]:
    """Compila y ejecuta el código del módulo y devuelve la función del nodo."""
    filename = filename_for(label)
    namespace = build_namespace()
    try:
        exec(compile(factory_source(code, function_name), filename, "exec"), namespace)  # noqa: S102
        return namespace[FACTORY_NAME]()
    except Exception as exc:
        raise CustomNodeError(describe_error(exc, filename)) from exc


def describe_error(exc: BaseException, filename: str) -> str:
    """Mensaje de un error del código del usuario, con la línea de su código si se conoce."""
    line = None
    if isinstance(exc, SyntaxError) and exc.filename == filename and exc.lineno:
        line = exc.lineno - 1
    for frame in traceback.extract_tb(exc.__traceback__):
        if frame.filename == filename and frame.lineno:
            line = frame.lineno - 1  # el último = el más interno dentro del código del usuario
    text = str(exc).strip()
    message = f"{type(exc).__name__}: {text}" if text else type(exc).__name__
    if "read-only" in text:
        message += " (las imágenes de entrada son de solo lectura: usa imagen.copy())"
    if line is not None and line > 0:
        message += f" — línea {line} del código del nodo"
    return message


def call_user_function(fn: Callable[..., Any], kwargs: dict[str, Any], label: str) -> Any:
    try:
        return fn(**kwargs)
    except Exception as exc:
        raise CustomNodeError(describe_error(exc, filename_for(label))) from exc


def coerce_results(value, types, label):
    """Normaliza lo que devolvió la función de un nodo a los tipos de sus salidas."""

    def fail(position, expected, item):
        where = f"la salida {position}" if len(types) > 1 else "la salida"
        raise ValueError(f"{label}: {where} debe ser {expected}, no {type(item).__name__}")

    def one(kind, item, position):
        if kind == "Any":
            return item
        if kind == "Image":
            if not isinstance(item, np.ndarray):
                fail(position, "una imagen (np.ndarray)", item)
            image = item[:, :, 0] if item.ndim == 3 and item.shape[2] == 1 else item
            if (
                image.size == 0
                or image.ndim not in (2, 3)
                or (image.ndim == 3 and image.shape[2] not in (3, 4))
            ):
                raise ValueError(
                    f"{label}: la imagen devuelta tiene una forma no válida {item.shape}"
                )
            if image.dtype == np.bool_:
                return image.astype(np.uint8) * 255
            if image.dtype != np.uint8:
                return np.clip(np.rint(image), 0, 255).astype(np.uint8)
            return image
        if kind == "Float":
            try:
                return float(item)
            except (TypeError, ValueError):
                fail(position, "un número decimal", item)
        if kind == "Integer":
            if isinstance(item, (bool, int, np.integer, np.bool_)):
                return int(item)
            if isinstance(item, (float, np.floating)) and float(item).is_integer():
                return int(item)
            fail(position, "un entero", item)
        if kind == "Boolean":
            if isinstance(item, (bool, np.bool_)) or item in (0, 1):
                return bool(item)
            fail(position, "verdadero o falso", item)
        if kind == "String":
            if not isinstance(item, str):
                fail(position, "un texto", item)
            return item
        if kind in ("Color", "Vector2", "Vector3"):
            size = 2 if kind == "Vector2" else 3
            try:
                parts = [float(c) for c in item]
            except (TypeError, ValueError):
                fail(position, f"una secuencia de {size} números", item)
            if len(parts) != size:
                raise ValueError(f"{label}: {kind} necesita {size} valores y recibió {len(parts)}")
            if kind == "Color":
                return tuple(max(0, min(255, int(round(c)))) for c in parts)
            return tuple(parts)
        return item

    if not types:
        return ()
    if len(types) == 1:
        values = (value,)
    else:
        if not isinstance(value, (tuple, list)) or len(value) != len(types):
            got = len(value) if isinstance(value, (tuple, list)) else type(value).__name__
            raise ValueError(
                f"{label}: la función debe devolver {len(types)} valores y devolvió {got}"
            )
        values = tuple(value)
    return tuple(
        one(kind, item, i + 1) for i, (kind, item) in enumerate(zip(types, values, strict=True))
    )
