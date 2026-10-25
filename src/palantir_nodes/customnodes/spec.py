"""Definición persistente de un nodo personalizado."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

TYPE_ID_PREFIX = "custom."
MAX_LABEL = 60
MAX_CATEGORY = 40


def slugify(text: str) -> str:
    """Identificador ASCII en minúsculas a partir de un nombre (``Mi ñ`` → ``mi_n``)."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", folded.lower()).strip("_")
    return slug or "nodo"


@dataclass
class CustomNodeSpec:
    id: str  # type_id del nodo: "custom.<slug>"; no cambia aunque se renombre
    label: str
    category: str
    code: str
    description: str = ""
    always_run: bool = False  # sin caché: se ejecuta en cada pasada (p. ej. si usa azar)

    @property
    def code_hash(self) -> str:
        return hashlib.sha1(self.code.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "description": self.description,
            "always_run": self.always_run,
            "code": self.code,
        }

    @classmethod
    def from_dict(cls, data: Any) -> CustomNodeSpec:
        """Construye la definición desde JSON. Lanza ``ValueError`` si faltan datos."""
        if not isinstance(data, dict):
            raise ValueError("la definición no es un objeto")
        for key in ("id", "label", "category", "code"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"falta '{key}' o no es texto")
        if not data["id"].startswith(TYPE_ID_PREFIX):
            raise ValueError(f"el id debe empezar por '{TYPE_ID_PREFIX}'")
        description = data.get("description", "")
        always_run = data.get("always_run", False)
        if not isinstance(description, str) or not isinstance(always_run, bool):
            raise ValueError("'description' o 'always_run' tienen un tipo inválido")
        return cls(
            data["id"],
            data["label"].strip(),
            data["category"].strip(),
            data["code"],
            description,
            always_run,
        )
