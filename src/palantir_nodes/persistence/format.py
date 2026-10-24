"""Identificación, versión y migraciones del formato de proyecto."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from palantir_nodes.core.errors import PalantirError

FORMAT_NAME = "palantir-nodes"
CURRENT_VERSION = 1

# Migraciones: ``{versión_origen: función}``. Cada función recibe el diccionario del
# proyecto en esa versión y lo devuelve en la siguiente (con ``version`` actualizado).
# Al cambiar el formato: subir CURRENT_VERSION y añadir aquí la migración (N -> N+1).
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ProjectFormatError(PalantirError):
    """El archivo no es un proyecto válido (o no se puede leer/migrar)."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        self.problems = problems or []
        super().__init__(message)


def migrate(
    data: dict[str, Any],
    *,
    current: int = CURRENT_VERSION,
    migrations: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Valida la cabecera y lleva ``data`` a la versión ``current``."""
    migrations = MIGRATIONS if migrations is None else migrations
    if not isinstance(data, dict):
        raise ProjectFormatError("El archivo no contiene un proyecto (se esperaba un objeto JSON)")
    if data.get("format") != FORMAT_NAME:
        raise ProjectFormatError(
            f"No es un proyecto de Palantir Nodes (campo 'format' = {data.get('format')!r})"
        )
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ProjectFormatError(f"Versión de formato inválida: {version!r}")
    if version > current:
        raise ProjectFormatError(
            f"El proyecto usa el formato v{version}, más nuevo que el que entiende esta "
            f"versión (v{current}). Actualiza Palantir Nodes para abrirlo."
        )
    while version < current:
        step = migrations.get(version)
        if step is None:
            raise ProjectFormatError(f"No hay migración del formato v{version} a v{version + 1}")
        data = step(dict(data))
        if data.get("version") != version + 1:
            raise ProjectFormatError(
                f"La migración v{version}→v{version + 1} no actualizó 'version'"
            )
        version += 1
    return data
