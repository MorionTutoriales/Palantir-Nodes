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
from palantir_nodes.core.graph import (
    FRAME_DEFAULT_COLOR,
    Frame,
    Graph,
    Link,
    normalize_frame_fields,
)
from palantir_nodes.customnodes.spec import CustomNodeSpec
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
    previews: bool = True
    zoom: float = 1.0
    center: tuple[float, float] = (0.0, 0.0)
    # Librerías adicionales activadas en el proyecto.
    libraries: list[str] = field(default_factory=list)
    pinned_node: str | None = None  # nodo en el que estaba fijado el visor
    preserved_nodes: list[dict[str, Any]] = field(default_factory=list)
    preserved_links: list[dict[str, Any]] = field(default_factory=list)
    # Definiciones de nodos personalizados incrustadas en el archivo y aún no importadas.
    custom_nodes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def dump(
    graph: Graph,
    project: ProjectData,
    app_version: str = "",
    custom_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Diccionario JSON del proyecto.

    ``custom_nodes`` son las definiciones (``CustomNodeSpec.to_dict``) de los nodos
    personalizados que usa el grafo, para que el proyecto se pueda abrir en otro equipo.
    """
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
        "settings": {"auto_run": project.auto_run, "previews": project.previews},
        "editor": {
            "zoom": project.zoom,
            "center": [project.center[0], project.center[1]],
            "pinned_node": project.pinned_node,
        },
        "nodes": nodes,
        "links": links,
        "frames": [frame.to_dict() for frame in graph.frames.values()],
        "libraries": list(project.libraries),
        "custom_nodes": list(custom_nodes or []),
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
        for key in ("nodes", "links", "frames")
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
    if isinstance(settings.get("previews"), bool):
        project.previews = settings["previews"]
    editor = data.get("editor") if isinstance(data.get("editor"), dict) else {}
    zoom = _number(editor.get("zoom"))
    if zoom is not None and zoom > 0:
        project.zoom = zoom
    pinned = editor.get("pinned_node")
    if isinstance(pinned, str) and pinned:
        project.pinned_node = pinned
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

    specs, spec_warnings = embedded_custom_nodes(data)
    project.custom_nodes = [spec.to_dict() for spec in specs]
    warnings.extend(spec_warnings)

    # 'frames' es opcional: los proyectos anteriores a los frames simplemente no lo tienen.
    for index, raw in enumerate(data.get("frames", []), start=1):
        _load_frame(graph, raw, index, warnings)
    return graph, project


def embedded_custom_nodes(data: dict[str, Any]) -> tuple[list[CustomNodeSpec], list[str]]:
    """Definiciones de nodos personalizados incrustadas en el proyecto (las inválidas se omiten)."""
    raw = data.get("custom_nodes", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return [], ["'custom_nodes' no es una lista (se ignora)"]
    specs: list[CustomNodeSpec] = []
    warnings: list[str] = []
    for index, item in enumerate(raw, start=1):
        try:
            specs.append(CustomNodeSpec.from_dict(item))
        except ValueError as exc:
            warnings.append(f"Nodo personalizado incrustado #{index} omitido: {exc}")
    return specs, warnings


def embedded_libraries(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Identificadores de las librerías que el proyecto tiene activadas (y avisos)."""
    raw = data.get("libraries", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return [], ["'libraries' no es una lista (se ignora)"]
    ids: list[str] = []
    warnings: list[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            if item not in ids:
                ids.append(item)
        else:
            warnings.append(f"Librería con un identificador inválido ({item!r}) omitida")
    return ids, warnings


_FRAME_NUMBERS = ("x", "y", "width", "height")


def _load_frame(graph: Graph, raw: Any, index: int, warnings: list[str]) -> None:
    where = f"Frame #{index}"
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
        warnings.append(f"{where}: formato inválido (se omite)")
        return
    numbers = {name: _number(raw.get(name)) for name in _FRAME_NUMBERS}
    if any(value is None for value in numbers.values()):
        warnings.append(f"{where}: posición o tamaño inválidos (se omite)")
        return
    fields: dict[str, Any] = dict(numbers)
    for name, default in (("title", "Frame"), ("color", FRAME_DEFAULT_COLOR)):
        if name not in raw:  # opcional: se usa el valor por defecto sin avisar
            fields[name] = default
            continue
        try:
            fields[name] = normalize_frame_fields({name: raw.get(name)})[name]
        except PalantirError:
            warnings.append(f"{where}: {name} inválido; se usa '{default}'")
            fields[name] = default
    try:
        graph.add_frame(Frame(raw["id"], **fields))
    except PalantirError as exc:
        warnings.append(f"{where} omitido: {exc}")
