"""Registro de tipos de nodo y descubrimiento de plugins."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from importlib.metadata import entry_points

from palantir_nodes.core.errors import ParamValidationError, RegistryError, UnknownNodeTypeError
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.categories import get_category

# Grupo de entry points para plugins externos. Cada entry point puede apuntar a un
# módulo (que registra sus nodos con @register_node al importarse) o a una función
# ``register(registry)``.
ENTRY_POINT_GROUP = "palantir_nodes.nodes"

NodeType = type[NodeDefinition]


def _validate_definition(cls: NodeType) -> None:
    if not (isinstance(cls, type) and issubclass(cls, NodeDefinition)):
        raise RegistryError(f"{cls!r} no es una subclase de NodeDefinition")
    name = cls.__name__
    if not cls.type_id:
        raise RegistryError(f"{name}: falta 'type_id'")
    if not cls.label:
        raise RegistryError(f"{name}: falta 'label'")
    if not cls.category:
        raise RegistryError(f"{name}: falta 'category'")
    for group, specs in (
        ("entradas", cls.inputs),
        ("salidas", cls.outputs),
        ("parámetros", cls.params),
    ):
        names = [spec.name for spec in specs]
        if len(names) != len(set(names)):
            raise RegistryError(f"{name}: nombres duplicados en {group}: {names}")
    try:
        cls.default_params()
        cls.default_input_values()
    except ParamValidationError as exc:
        raise RegistryError(f"{name}: valor por defecto inválido: {exc}") from exc


class NodeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, NodeType] = {}

    def register(self, cls: NodeType) -> NodeType:
        _validate_definition(cls)
        existing = self._types.get(cls.type_id)
        if existing is not None and existing is not cls:
            raise RegistryError(
                f"El type_id '{cls.type_id}' ya está registrado por {existing.__name__}"
            )
        self._types[cls.type_id] = cls
        return cls

    def get(self, type_id: str) -> NodeType | None:
        return self._types.get(type_id)

    def require(self, type_id: str) -> NodeType:
        cls = self._types.get(type_id)
        if cls is None:
            raise UnknownNodeTypeError(f"Tipo de nodo desconocido: '{type_id}'")
        return cls

    def __contains__(self, type_id: object) -> bool:
        return type_id in self._types

    def __iter__(self) -> Iterator[NodeType]:
        return iter(self._types.values())

    def __len__(self) -> int:
        return len(self._types)

    def copy(self) -> NodeRegistry:
        clone = NodeRegistry()
        clone._types = dict(self._types)
        return clone

    def by_category(self) -> dict[str, list[NodeType]]:
        """Tipos agrupados por categoría, en el orden de los menús."""
        groups: dict[str, list[NodeType]] = {}
        ordered = sorted(
            self._types.values(),
            key=lambda c: (get_category(c.category).order, c.category),
        )
        for cls in ordered:
            groups.setdefault(cls.category, []).append(cls)
        for members in groups.values():
            members.sort(key=lambda c: c.label.lower())
        return groups

    def search(self, query: str) -> list[NodeType]:
        """Busca por nombre, categoría o identificador. Prioriza coincidencias al inicio."""
        q = query.strip().lower()
        if not q:
            return [cls for members in self.by_category().values() for cls in members]
        scored: list[tuple[int, str, NodeType]] = []
        for cls in self._types.values():
            label = cls.label.lower()
            if label.startswith(q):
                score = 0
            elif any(word.startswith(q) for word in label.split()):
                score = 1
            elif q in label:
                score = 2
            elif q in cls.category.lower() or q in cls.type_id.lower():
                score = 3
            else:
                continue
            scored.append((score, label, cls))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [cls for _, _, cls in scored]

    def load_entry_points(self, group: str = ENTRY_POINT_GROUP) -> list[str]:
        """Carga plugins instalados. Devuelve los mensajes de error (no lanza)."""
        errors: list[str] = []
        for ep in entry_points(group=group):
            try:
                obj = ep.load()
                if callable(obj):
                    obj(self)
            except Exception as exc:  # un plugin defectuoso no debe impedir arrancar
                errors.append(f"Plugin '{ep.name}': {exc}")
        return errors


default_registry = NodeRegistry()


def register_node(cls: NodeType) -> NodeType:
    """Decorador que registra un tipo de nodo en el registro por defecto."""
    return default_registry.register(cls)


_builtins_loaded = False


def load_builtin_nodes() -> NodeRegistry:
    """Importa la biblioteca de nodos incluida y devuelve el registro por defecto."""
    global _builtins_loaded
    if not _builtins_loaded:
        importlib.import_module("palantir_nodes.nodes.library")
        _builtins_loaded = True
    return default_registry
