"""Biblioteca de nodos personalizados: validación, registro en el editor y guardado.

Las definiciones se guardan en un JSON en la carpeta de configuración del usuario. Una
entrada con código que ya no es válido (p. ej. editada a mano) no se registra pero se
conserva en la biblioteca para poder corregirla desde el gestor.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from palantir_nodes.core.errors import PalantirError
from palantir_nodes.customnodes.analysis import Analysis, Issue, analyze
from palantir_nodes.customnodes.factory import build_node_class
from palantir_nodes.customnodes.spec import (
    MAX_CATEGORY,
    MAX_LABEL,
    TYPE_ID_PREFIX,
    CustomNodeSpec,
    slugify,
)
from palantir_nodes.nodes.categories import ensure_category
from palantir_nodes.nodes.registry import NodeRegistry
from palantir_nodes.persistence.files import write_project
from palantir_nodes.preferences import config_dir

LIBRARY_FORMAT = "palantir-nodes-custom-library"
LIBRARY_VERSION = 1


class CustomNodeValidationError(PalantirError):
    """La definición del nodo no es válida (``issues`` explica por qué)."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))


def default_library_path() -> Path:
    return config_dir() / "custom_nodes.json"


class CustomNodeLibrary:
    def __init__(self, registry: NodeRegistry, path: str | os.PathLike[str] | None = None) -> None:
        self.registry = registry
        self._path = Path(path) if path is not None else None
        self.entries: dict[str, CustomNodeSpec] = {}
        self.broken: dict[str, list[Issue]] = {}

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else default_library_path()

    # -- consulta ----------------------------------------------------------------------

    def get(self, type_id: str) -> CustomNodeSpec | None:
        return self.entries.get(type_id)

    def is_custom(self, type_id: str) -> bool:
        return type_id in self.entries

    def ordered(self) -> list[CustomNodeSpec]:
        return sorted(self.entries.values(), key=lambda s: (s.category.lower(), s.label.lower()))

    def categories(self) -> list[str]:
        """Categorías disponibles (las del editor y las de los nodos personalizados)."""
        names = {cls.category for cls in self.registry}
        names.update(spec.category for spec in self.entries.values())
        return sorted(names, key=lambda n: n.lower())

    # -- validación --------------------------------------------------------------------

    def validate(self, spec: CustomNodeSpec) -> tuple[list[Issue], Analysis]:
        """Comprueba una definición. No la guarda ni la registra."""
        issues: list[Issue] = []
        label = spec.label
        if not label.strip():
            issues.append(Issue("El nodo necesita un nombre."))
        elif label != label.strip() or len(label) > MAX_LABEL:
            issues.append(
                Issue(
                    f"El nombre no puede tener espacios en los extremos ni más de {MAX_LABEL} caracteres."
                )
            )
        else:
            taken = {cls.label.lower(): cls.type_id for cls in self.registry}
            owner = taken.get(label.lower())
            if owner is not None and owner != spec.id:
                issues.append(Issue(f"Ya existe un nodo llamado '{label}'."))
        category = spec.category
        if not category.strip():
            issues.append(Issue("Elige una categoría."))
        elif category != category.strip() or len(category) > MAX_CATEGORY:
            issues.append(
                Issue(
                    f"La categoría no puede tener espacios en los extremos ni más de {MAX_CATEGORY} caracteres."
                )
            )
        analysis = analyze(spec.code)
        issues.extend(analysis.errors)
        return issues, analysis

    # -- altas, cambios y bajas --------------------------------------------------------

    def new_id(self, label: str) -> str:
        base = f"{TYPE_ID_PREFIX}{slugify(label)}"
        candidate, n = base, 2
        while candidate in self.entries or candidate in self.registry:
            candidate, n = f"{base}_{n}", n + 1
        return candidate

    def create(
        self,
        label: str,
        category: str,
        code: str,
        description: str = "",
        always_run: bool = False,
    ) -> CustomNodeSpec:
        """Crea, registra y guarda un nodo nuevo. Lanza ``CustomNodeValidationError``."""
        spec = CustomNodeSpec(self.new_id(label), label, category, code, description, always_run)
        self._register(spec)
        self.entries[spec.id] = spec
        self.broken.pop(spec.id, None)
        self.save()
        return spec

    def update(self, spec: CustomNodeSpec) -> None:
        """Cambia un nodo existente (mismo ``id``) y lo vuelve a registrar."""
        if spec.id not in self.entries:
            raise KeyError(spec.id)
        self._register(spec)
        self.entries[spec.id] = spec
        self.broken.pop(spec.id, None)
        self.save()

    def remove(self, type_id: str) -> None:
        if type_id not in self.entries:
            raise KeyError(type_id)
        self.registry.unregister(type_id)
        del self.entries[type_id]
        self.broken.pop(type_id, None)
        self.save()

    def duplicate(self, type_id: str) -> CustomNodeSpec:
        original = self.entries[type_id]
        label, n = f"{original.label} (copia)", 2
        taken = {cls.label.lower() for cls in self.registry}
        while label.lower() in taken:
            label, n = f"{original.label} (copia {n})", n + 1
        return self.create(
            label, original.category, original.code, original.description, original.always_run
        )

    def import_spec(self, spec: CustomNodeSpec) -> bool:
        """Añade un nodo traído de un proyecto. ``False`` si ya estaba (mismo ``id``).

        Si el nombre choca con otro nodo, se le añade un sufijo. Lanza
        ``CustomNodeValidationError`` si su código no es válido.
        """
        if spec.id in self.entries:
            return False
        imported = replace(spec)
        taken = {cls.label.lower() for cls in self.registry}
        base, n = imported.label, 2
        while imported.label.lower() in taken:
            imported.label, n = f"{base} ({n})", n + 1
        self._register(imported)
        self.entries[imported.id] = imported
        self.save()
        return True

    def _register(self, spec: CustomNodeSpec) -> None:
        issues, analysis = self.validate(spec)
        if issues:
            raise CustomNodeValidationError(issues)
        try:
            node_class = build_node_class(spec, analysis)
            self.registry.replace(node_class)
        except PalantirError as exc:
            raise CustomNodeValidationError([Issue(str(exc))]) from exc
        ensure_category(spec.category)

    # -- persistencia ------------------------------------------------------------------

    def save(self) -> None:
        """Guarda la biblioteca de forma atómica. Lanza ``OSError`` si no es posible."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_project(
            self.path,
            {
                "format": LIBRARY_FORMAT,
                "version": LIBRARY_VERSION,
                "nodes": [spec.to_dict() for spec in self.ordered()],
            },
        )

    def load(self) -> list[str]:
        """Carga y registra los nodos guardados. Devuelve avisos; nunca lanza."""
        warnings: list[str] = []
        if not self.path.exists():
            return warnings
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [f"No se pudo leer la biblioteca de nodos personalizados ({exc})"]
        raw_nodes = data.get("nodes") if isinstance(data, dict) else None
        if not isinstance(raw_nodes, list):
            return ["La biblioteca de nodos personalizados no tiene el formato esperado"]
        for index, raw in enumerate(raw_nodes, start=1):
            try:
                spec = CustomNodeSpec.from_dict(raw)
            except ValueError as exc:
                warnings.append(f"Nodo personalizado #{index} omitido: {exc}")
                continue
            if spec.id in self.entries:
                warnings.append(f"Nodo personalizado '{spec.label}' repetido; se ignora la copia")
                continue
            self.entries[spec.id] = spec
            try:
                self._register(spec)
            except CustomNodeValidationError as exc:
                self.broken[spec.id] = exc.issues
                warnings.append(
                    f"El nodo personalizado '{spec.label}' tiene errores: {exc.issues[0]}"
                )
        return warnings
