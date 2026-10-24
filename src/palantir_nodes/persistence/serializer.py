"""Conversión entre el grafo en memoria y el diccionario JSON del proyecto.

La carga nunca falla por un nodo o conexión individual: lo que no se puede aplicar se
omite con un aviso. Los nodos de tipos desconocidos (p. ej. de un plugin no instalado)
se conservan tal cual y se vuelven a escribir al guardar, para no perder información.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from palantir_nodes.core.errors import PalantirError
from palantir_nodes.core.graph import Graph, Link
from palantir_nodes.nodes.registry import NodeRegistry
from palantir_nodes.persistence.format import (
    CURRENT_VERSION,
    FORMAT_NAME,
    ProjectFormatError,
    migrate,
)

_LINK_FIELDS = ("id", "src_node", "src_socket", "dst_node", "dst_socket")


@dataclass
class ProjectData:
    """Estado del proyecto que no pertenece al grafo."""

    name: str = ""
    auto_run: bool = True
    zoom: float = 1.0
    center: tuple[float, float] = (0.0, 0.0)
    preserved_nodes: list[dict[str, Any]] = field(default_factory=list)
    preserved_links: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def dump(graph: Graph, project: ProjectData, app_version: str = "") -> dict[str, Any]:
    nodes = [node.to_dict() for node in graph.nodes.values()] + list(project.preserved_nodes)
    links = [link.to_dict() for link in graph.links.values()] + list(project.preserved_links)
    return {
        "format": FORMAT_NAME,
        "version": CURRENT_VERSION,
        "meta": {
            "name": project.name,
            "app_version": app_version,
            "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        "settings": {"auto_run": project.auto_run},
        "editor": {
            "zoom": project.zoom,
            "center": [project.center[0], project.center[1]],
        },
        "nodes": nodes,
        "links": links,
    }


# -- carga -------------------------------------------------------------------------------


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _clean_values(
    raw: Any, spec_for, label: str, warnings: list[str], where: str
) -> dict[str, Any]:
    """Valida un diccionario de parámetros; descarta lo inválido con un aviso."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        warnings.append(f"{where}: '{label}' no es un objeto; se usan los valores por defecto")
        return {}
    clean: dict[str, Any] = {}
    for name, value in raw.items():
        spec = spec_for(name)
        if spec is None:
            warnings.append(f"{where}: {label} desconocido '{name}' (se ignora)")
            continue
        try:
            clean[name] = spec.coerce(value)
        except PalantirError as exc:
            warnings.append(f"{where}: {exc}; se usa el valor por defecto")
    return clean


def load(data: dict[str, Any], registry: NodeRegistry) -> tuple[Graph, ProjectData]:
    """Construye un grafo nuevo a partir del proyecto.

    Lanza :class:`ProjectFormatError` solo si el archivo en conjunto no es utilizable.
    """
    data = migrate(data)
    problems = [
        f"'{key}' debe ser una lista"
        for key in ("nodes", "links")
        if not isinstance(data.get(key, []), list)
    ]
    if problems:
        raise ProjectFormatError(
            "Estructura de proyecto inválida: " + "; ".join(problems), problems
        )

    graph = Graph(registry)
    project = ProjectData()
    warnings = project.warnings

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    project.name = str(meta.get("name", "")) if meta else ""
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
    if isinstance(settings.get("auto_run"), bool):
        project.auto_run = settings["auto_run"]
    editor = data.get("editor") if isinstance(data.get("editor"), dict) else {}
    zoom = _number(editor.get("zoom"))
    if zoom is not None and zoom > 0:
        project.zoom = zoom
    center = editor.get("center")
    if isinstance(center, list) and len(center) == 2:
        cx, cy = _number(center[0]), _number(center[1])
        if cx is not None and cy is not None:
            project.center = (cx, cy)

    seen_ids: set[str] = set()
    preserved_ids: set[str] = set()
    for index, raw in enumerate(data.get("nodes", []), start=1):
        if not isinstance(raw, dict):
            warnings.append(f"Nodo #{index}: no es un objeto (se omite)")
            continue
        node_id, type_id = raw.get("id"), raw.get("type_id")
        if not isinstance(node_id, str) or not node_id or not isinstance(type_id, str):
            warnings.append(f"Nodo #{index}: faltan 'id' o 'type_id' (se omite)")
            continue
        if node_id in seen_ids:
            warnings.append(f"Nodo #{index}: id duplicado '{node_id}' (se omite)")
            continue
        seen_ids.add(node_id)

        definition = registry.get(type_id)
        if definition is None:
            project.preserved_nodes.append(raw)
            preserved_ids.add(node_id)
            warnings.append(
                f"Tipo de nodo desconocido '{type_id}': no se muestra, pero se conserva al guardar"
            )
            continue

        where = f"{definition.label} ({node_id[:8]})"
        position = raw.get("position", [0.0, 0.0])
        x = y = None
        if isinstance(position, list) and len(position) == 2:
            x, y = _number(position[0]), _number(position[1])
        if x is None or y is None:
            warnings.append(f"{where}: posición inválida; se coloca en el origen")
            x = y = 0.0

        params = _clean_values(raw.get("params"), definition.param, "parámetro", warnings, where)

        def input_spec(name: str, definition=definition):
            spec = definition.input(name)
            return spec.value_spec() if spec else None

        input_values = _clean_values(
            raw.get("input_values"), input_spec, "valor de entrada", warnings, where
        )
        graph.add_node(type_id, (x, y), node_id=node_id, params=params, input_values=input_values)

    seen_links: set[str] = set()
    for index, raw in enumerate(data.get("links", []), start=1):
        if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) for k in _LINK_FIELDS):
            warnings.append(f"Conexión #{index}: formato inválido (se omite)")
            continue
        link = Link.from_dict(raw)
        if link.src_node in preserved_ids or link.dst_node in preserved_ids:
            project.preserved_links.append(raw)  # toca un nodo desconocido: se conserva
            continue
        if link.id in seen_links:
            warnings.append(f"Conexión #{index}: id duplicado '{link.id}' (se omite)")
            continue
        seen_links.add(link.id)
        try:
            graph.add_link_object(link)
        except PalantirError as exc:
            warnings.append(f"Conexión #{index} omitida: {exc}")
    return graph, project
