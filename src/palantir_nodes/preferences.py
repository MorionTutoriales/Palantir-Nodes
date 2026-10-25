"""Preferencias de la aplicación (no del proyecto). Este módulo no depende de Qt.

Se guardan en un JSON en la carpeta de configuración del usuario. Un archivo ausente,
dañado o con valores inválidos nunca impide arrancar: se usan los valores por defecto y se
informa de lo ocurrido.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from palantir_nodes.persistence.files import write_project

PREFERENCES_FORMAT = "palantir-nodes-preferences"
PREFERENCES_VERSION = 1
CONFIG_DIR_ENV = "PALANTIR_NODES_CONFIG_DIR"  # permite aislar el archivo (p. ej. en pruebas)

ZOOM_SPEED_RANGE = (1.05, 1.50)
PREVIEW_RATE_RANGE = (5, 30)


def config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "PalantirNodes"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "palantir-nodes"


def preferences_path() -> Path:
    return config_dir() / "preferences.json"


@dataclass
class Preferences:
    reopen_last_project: bool = False
    last_project: str = ""
    show_grid: bool = True
    zoom_speed: float = 1.15  # factor por paso de la rueda
    auto_run_default: bool = True  # valor para proyectos nuevos
    previews_default: bool = True  # valor para proyectos nuevos
    preview_rate_hz: int = 15  # miniaturas por segundo como máximo en tiempo real
    # Carpetas extra donde los nodos personalizados buscan módulos al hacer ``import``.
    import_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> tuple[Preferences, list[str]]:
        """Construye las preferencias desde un diccionario, corrigiendo lo inválido."""
        warnings: list[str] = []
        prefs = cls()
        if not isinstance(data, dict):
            return prefs, [
                "El archivo de preferencias no contiene un objeto; se usan los valores por defecto"
            ]
        for item in fields(cls):
            if item.name not in data:
                continue
            value = data[item.name]
            default = getattr(prefs, item.name)
            try:
                setattr(prefs, item.name, _coerce(item.name, value, default, warnings))
            except (TypeError, ValueError):
                warnings.append(
                    f"Preferencia '{item.name}' inválida ({value!r}); se usa {default!r}"
                )
        return prefs, warnings


MAX_IMPORT_PATHS = 50


def _coerce(name: str, value: Any, default: Any, warnings: list[str]) -> Any:
    if isinstance(default, list):
        if not isinstance(value, list):
            raise TypeError
        clean = list(dict.fromkeys(v.strip() for v in value if isinstance(v, str) and v.strip()))
        if len(clean) != len(value):
            warnings.append(f"Preferencia '{name}': se omitieron entradas inválidas o repetidas")
        return clean[:MAX_IMPORT_PATHS]
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise TypeError
        return value
    if isinstance(default, str):
        if not isinstance(value, str):
            raise TypeError
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TypeError
    low, high = ZOOM_SPEED_RANGE if name == "zoom_speed" else PREVIEW_RATE_RANGE
    clamped = min(max(value, low), high)
    if clamped != value:
        warnings.append(f"Preferencia '{name}' fuera de rango ({value}); se usa {clamped}")
    return float(clamped) if isinstance(default, float) else int(round(clamped))


def load_preferences(path: str | os.PathLike[str] | None = None) -> tuple[Preferences, list[str]]:
    """Lee las preferencias. Devuelve ``(preferencias, avisos)``; nunca lanza."""
    path = Path(path) if path is not None else preferences_path()
    if not path.exists():
        return Preferences(), []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Preferences(), [
            f"No se pudieron leer las preferencias ({exc}); se usan los valores por defecto"
        ]
    if isinstance(data, dict) and data.get("format") == PREFERENCES_FORMAT:
        data = data.get("preferences", {})
    return Preferences.from_dict(data)


def save_preferences(prefs: Preferences, path: str | os.PathLike[str] | None = None) -> None:
    """Guarda las preferencias de forma atómica. Lanza ``OSError`` si no es posible."""
    path = Path(path) if path is not None else preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_project(
        path,
        {
            "format": PREFERENCES_FORMAT,
            "version": PREFERENCES_VERSION,
            "preferences": prefs.to_dict(),
        },
    )
