"""Carpetas extra donde buscar módulos de Python para los nodos personalizados.

El código de un nodo puede hacer ``import mi_modulo``: Python lo busca en el entorno de la
aplicación y, además, en estas carpetas (que se añaden al **final** de ``sys.path`` para que
nunca tapen los paquetes que la aplicación ya usa).
"""

from __future__ import annotations

import importlib
import os
import sys

_applied: list[str] = []


def normalize(path: str) -> str:
    path = path.strip()
    return os.path.normpath(os.path.expanduser(path)) if path else ""  # «» no es la carpeta actual


def apply_import_paths(paths: list[str]) -> list[str]:
    """Deja en ``sys.path`` exactamente ``paths`` (de los que añadió esta función).

    Quita los que se aplicaron antes y no están ahora, y no toca los que ya estaban en
    ``sys.path`` por su cuenta. Devuelve las carpetas que quedaron aplicadas.
    """
    for old in _applied:
        while old in sys.path:
            sys.path.remove(old)
    _applied.clear()
    for path in paths:
        folder = normalize(path)
        if folder and folder not in sys.path:
            sys.path.append(folder)
            _applied.append(folder)
    importlib.invalidate_caches()
    return list(_applied)


def applied_paths() -> list[str]:
    return list(_applied)


def missing_paths(paths: list[str]) -> list[str]:
    """Las que no existen o no son carpetas."""
    return [p for p in paths if not os.path.isdir(normalize(p))]
