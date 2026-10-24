"""Lectura y escritura de archivos de proyecto."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from palantir_nodes.persistence.format import ProjectFormatError

MAX_PROJECT_BYTES = 64 * 1024 * 1024


def read_project(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Lee el JSON de un proyecto o lanza :class:`ProjectFormatError` con el motivo."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ProjectFormatError(f"No se puede abrir '{path.name}': {exc.strerror or exc}") from exc
    if size > MAX_PROJECT_BYTES:
        raise ProjectFormatError(f"'{path.name}' es demasiado grande para ser un proyecto")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectFormatError(f"'{path.name}' no es un archivo de texto UTF-8") from exc
    except OSError as exc:
        raise ProjectFormatError(f"No se puede leer '{path.name}': {exc.strerror or exc}") from exc
    if not text.strip():
        raise ProjectFormatError(f"'{path.name}' está vacío")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(
            f"'{path.name}' no es JSON válido (línea {exc.lineno}, columna {exc.colno}): {exc.msg}"
        ) from exc


def write_project(path: str | os.PathLike[str], data: dict[str, Any]) -> None:
    """Escribe el proyecto de forma atómica: el archivo anterior nunca queda a medias.

    Escribe a un temporal en la misma carpeta y lo renombra al terminar. Lanza ``OSError``
    si no se puede escribir y ``ValueError`` si los datos no son JSON válido (NaN, etc.).
    """
    path = Path(path)
    # Se serializa antes de tocar el disco: un dato inválido no destruye el archivo existente.
    text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
