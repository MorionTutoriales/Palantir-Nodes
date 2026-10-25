"""Modelo lógico del grafo: nodos, conexiones y eventos de cambio."""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from palantir_nodes.core.errors import ConnectionRejectedError, GraphError
from palantir_nodes.core.types import is_compatible
from palantir_nodes.core.validation import ConnectionCheck, check_connection

if TYPE_CHECKING:
    from palantir_nodes.nodes.base import NodeDefinition
    from palantir_nodes.nodes.registry import NodeRegistry


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class NodeInstance:
    id: str
    type_id: str
    position: tuple[float, float]
    params: dict[str, Any]
    input_values: dict[str, Any]
    definition: type[NodeDefinition] | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type_id": self.type_id,
            "position": [self.position[0], self.position[1]],
            "params": dict(self.params),
            "input_values": dict(self.input_values),
        }


@dataclass(frozen=True)
class Link:
    id: str
    src_node: str
    src_socket: str
    dst_node: str
    dst_socket: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "src_node": self.src_node,
            "src_socket": self.src_socket,
            "dst_node": self.dst_node,
            "dst_socket": self.dst_socket,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Link:
        return cls(
            str(data["id"]),
            str(data["src_node"]),
            str(data["src_socket"]),
            str(data["dst_node"]),
            str(data["dst_socket"]),
        )


FRAME_MIN_WIDTH = 80.0
FRAME_MIN_HEIGHT = 60.0
FRAME_DEFAULT_COLOR = "#4A6FA5"
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _finite(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GraphError(f"Frame: '{what}' debe ser un número finito")
    return float(value)


def normalize_frame_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Valida y normaliza campos de frame. Lanza :class:`GraphError` si alguno es inválido."""
    clean: dict[str, Any] = {}
    for name, value in fields.items():
        if name == "title":
            if not isinstance(value, str) or not value.strip():
                raise GraphError("Frame: el título no puede estar vacío")
            clean[name] = value.strip()
        elif name == "color":
            if not isinstance(value, str) or not _COLOR_RE.match(value):
                raise GraphError(f"Frame: color inválido {value!r} (se espera #RRGGBB)")
            clean[name] = value.upper()
        elif name in ("x", "y"):
            clean[name] = _finite(value, name)
        elif name == "width":
            clean[name] = max(FRAME_MIN_WIDTH, _finite(value, name))
        elif name == "height":
            clean[name] = max(FRAME_MIN_HEIGHT, _finite(value, name))
        else:
            raise GraphError(f"Frame: campo desconocido '{name}'")
    return clean


@dataclass
class Frame:
    """Rectángulo con título que agrupa nodos visualmente. No afecta al procesamiento."""

    id: str
    title: str = "Frame"
    color: str = FRAME_DEFAULT_COLOR
    x: float = 0.0
    y: float = 0.0
    width: float = 300.0
    height: float = 200.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "color": self.color,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    def copy(self) -> Frame:
        return Frame(**self.to_dict())


class GraphEventKind(Enum):
    NODE_ADDED = auto()
    NODE_REMOVED = auto()
    NODE_MOVED = auto()
    PARAM_CHANGED = auto()
    INPUT_VALUE_CHANGED = auto()
    LINK_ADDED = auto()
    LINK_REMOVED = auto()
    FRAME_ADDED = auto()
    FRAME_REMOVED = auto()
    FRAME_CHANGED = auto()
    # Cambió la definición de un tipo de nodo y se migraron sus instancias: reconstruir todo.
    REBUILT = auto()
    CLEARED = auto()


@dataclass(frozen=True)
class GraphEvent:
    kind: GraphEventKind
    node_id: str | None = None
    link: Link | None = None
    name: str | None = None
    frame_id: str | None = None


GraphListener = Callable[[GraphEvent], None]


class Graph:
    """Grafo de procesamiento independiente de la interfaz.

    Toda modificación pasa por estos métodos, que validan los datos y notifican a los
    suscriptores (la escena visual, el panel de propiedades y, más adelante, el motor).
    """

    def __init__(self, registry: NodeRegistry) -> None:
        self.registry = registry
        self._nodes: dict[str, NodeInstance] = {}
        self._links: dict[str, Link] = {}
        self._frames: dict[str, Frame] = {}
        self._listeners: list[GraphListener] = []

    # -- suscripción -------------------------------------------------------------------

    def subscribe(self, listener: GraphListener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: GraphListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _emit(self, event: GraphEvent) -> None:
        for listener in list(self._listeners):
            listener(event)

    # -- consultas ---------------------------------------------------------------------

    @property
    def nodes(self) -> Mapping[str, NodeInstance]:
        return MappingProxyType(self._nodes)

    @property
    def links(self) -> Mapping[str, Link]:
        return MappingProxyType(self._links)

    @property
    def frames(self) -> Mapping[str, Frame]:
        return MappingProxyType(self._frames)

    def frame(self, frame_id: str) -> Frame:
        try:
            return self._frames[frame_id]
        except KeyError:
            raise GraphError(f"No existe el frame '{frame_id}'") from None

    def node(self, node_id: str) -> NodeInstance:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise GraphError(f"No existe el nodo '{node_id}'") from None

    def link_to_input(self, node_id: str, socket: str) -> Link | None:
        for link in self._links.values():
            if link.dst_node == node_id and link.dst_socket == socket:
                return link
        return None

    def links_from_output(self, node_id: str, socket: str) -> list[Link]:
        return [
            link
            for link in self._links.values()
            if link.src_node == node_id and link.src_socket == socket
        ]

    def links_of_node(self, node_id: str) -> list[Link]:
        return [
            link
            for link in self._links.values()
            if link.src_node == node_id or link.dst_node == node_id
        ]

    def connected_inputs(self, node_id: str) -> set[str]:
        return {link.dst_socket for link in self._links.values() if link.dst_node == node_id}

    # -- nodos -------------------------------------------------------------------------

    def add_node(
        self,
        type_id: str,
        position: tuple[float, float] = (0.0, 0.0),
        *,
        node_id: str | None = None,
        params: Mapping[str, Any] | None = None,
        input_values: Mapping[str, Any] | None = None,
    ) -> NodeInstance:
        definition = self.registry.require(type_id)
        node_id = node_id or new_id()
        if node_id in self._nodes:
            raise GraphError(f"Ya existe un nodo con id '{node_id}'")

        values = definition.default_params()
        for name, value in (params or {}).items():
            spec = definition.param(name)
            if spec is not None:  # se ignoran parámetros que el tipo ya no declara
                values[name] = spec.coerce(value)

        inputs = definition.default_input_values()
        for name, value in (input_values or {}).items():
            spec = definition.input(name)
            value_spec = spec.value_spec() if spec else None
            if value_spec is not None:
                inputs[name] = value_spec.coerce(value)

        node = NodeInstance(
            node_id,
            type_id,
            (float(position[0]), float(position[1])),
            values,
            inputs,
            definition,
        )
        self._nodes[node_id] = node
        self._emit(GraphEvent(GraphEventKind.NODE_ADDED, node_id=node_id))
        return node

    def add_node_from_dict(self, data: Mapping[str, Any]) -> NodeInstance:
        position = data.get("position", (0.0, 0.0))
        return self.add_node(
            data["type_id"],
            (position[0], position[1]),
            node_id=data.get("id"),
            params=data.get("params"),
            input_values=data.get("input_values"),
        )

    def remove_node(self, node_id: str) -> tuple[NodeInstance, list[Link]]:
        """Elimina un nodo y sus conexiones. Devuelve lo eliminado."""
        node = self.node(node_id)
        removed = [self.remove_link(link.id) for link in self.links_of_node(node_id)]
        del self._nodes[node_id]
        self._emit(GraphEvent(GraphEventKind.NODE_REMOVED, node_id=node_id))
        return node, removed

    def move_node(self, node_id: str, position: tuple[float, float]) -> None:
        node = self.node(node_id)
        position = (float(position[0]), float(position[1]))
        if node.position != position:
            node.position = position
            self._emit(GraphEvent(GraphEventKind.NODE_MOVED, node_id=node_id))

    def set_param(self, node_id: str, name: str, value: Any) -> None:
        node = self.node(node_id)
        spec = node.definition.param(name) if node.definition else None
        if spec is None:
            raise GraphError(f"El nodo '{node.type_id}' no tiene el parámetro '{name}'")
        value = spec.coerce(value)
        if node.params.get(name) != value:
            node.params[name] = value
            self._emit(GraphEvent(GraphEventKind.PARAM_CHANGED, node_id=node_id, name=name))

    def set_input_value(self, node_id: str, name: str, value: Any) -> None:
        node = self.node(node_id)
        spec = node.definition.input(name) if node.definition else None
        value_spec = spec.value_spec() if spec else None
        if value_spec is None:
            raise GraphError(f"La entrada '{name}' no tiene valor editable")
        value = value_spec.coerce(value)
        if node.input_values.get(name) != value:
            node.input_values[name] = value
            self._emit(GraphEvent(GraphEventKind.INPUT_VALUE_CHANGED, node_id=node_id, name=name))

    # -- conexiones --------------------------------------------------------------------

    def can_connect(
        self, src_node: str, src_socket: str, dst_node: str, dst_socket: str
    ) -> ConnectionCheck:
        return check_connection(self, src_node, src_socket, dst_node, dst_socket)

    def add_link(
        self,
        src_node: str,
        src_socket: str,
        dst_node: str,
        dst_socket: str,
        *,
        link_id: str | None = None,
    ) -> Link:
        """Crea una conexión. La entrada debe estar libre (para reemplazar, elimina antes)."""
        check = check_connection(
            self, src_node, src_socket, dst_node, dst_socket, allow_replace=False
        )
        if not check:
            raise ConnectionRejectedError(check.reason)
        link = Link(link_id or new_id(), src_node, src_socket, dst_node, dst_socket)
        if link.id in self._links:
            raise GraphError(f"Ya existe una conexión con id '{link.id}'")
        self._links[link.id] = link
        self._emit(GraphEvent(GraphEventKind.LINK_ADDED, node_id=dst_node, link=link))
        return link

    def add_link_object(self, link: Link) -> Link:
        return self.add_link(
            link.src_node, link.src_socket, link.dst_node, link.dst_socket, link_id=link.id
        )

    def remove_link(self, link_id: str) -> Link:
        try:
            link = self._links.pop(link_id)
        except KeyError:
            raise GraphError(f"No existe la conexión '{link_id}'") from None
        self._emit(GraphEvent(GraphEventKind.LINK_REMOVED, node_id=link.dst_node, link=link))
        return link

    # -- migración de tipos ------------------------------------------------------------

    def nodes_of_type(self, type_id: str) -> list[NodeInstance]:
        return [node for node in self._nodes.values() if node.type_id == type_id]

    def migrate_node_type(self, type_id: str) -> list[str]:
        """Adapta los nodos de ``type_id`` a su definición actual del registro.

        Se conservan los valores cuyo nombre sigue existiendo y siguen siendo válidos; las
        conexiones cuyo socket ya no existe o dejó de ser compatible se eliminan. Devuelve
        los avisos de lo que se perdió.
        """
        definition = self.registry.require(type_id)
        notes: list[str] = []
        migrated = {node.id for node in self.nodes_of_type(type_id)}
        for node in self.nodes_of_type(type_id):
            old_params, old_inputs = node.params, node.input_values
            node.definition = definition
            node.params = definition.default_params()
            for name, value in old_params.items():
                spec = definition.param(name)
                if spec is not None:
                    try:
                        node.params[name] = spec.coerce(value)
                    except Exception:
                        notes.append(f"{definition.label}: '{name}' vuelve a su valor por defecto")
            node.input_values = definition.default_input_values()
            for name, value in old_inputs.items():
                spec = definition.input(name)
                value_spec = spec.value_spec() if spec else None
                if value_spec is not None:
                    try:
                        node.input_values[name] = value_spec.coerce(value)
                    except Exception:
                        notes.append(f"{definition.label}: '{name}' vuelve a su valor por defecto")
        for link in list(self._links.values()):
            if link.src_node not in migrated and link.dst_node not in migrated:
                continue
            src, dst = self._nodes[link.src_node], self._nodes[link.dst_node]
            out_spec = src.definition.output(link.src_socket)
            in_spec = dst.definition.input(link.dst_socket)
            if (
                out_spec is None
                or in_spec is None
                or not is_compatible(out_spec.type, in_spec.type)
            ):
                del self._links[link.id]
                notes.append(
                    f"Se eliminó la conexión {src.definition.label}.{link.src_socket} → "
                    f"{dst.definition.label}.{link.dst_socket}"
                )
        self._emit(GraphEvent(GraphEventKind.REBUILT))
        return notes

    def remove_nodes_of_type(self, type_id: str) -> int:
        """Elimina todos los nodos de ``type_id`` (y sus conexiones). Devuelve cuántos."""
        victims = [node.id for node in self.nodes_of_type(type_id)]
        for node_id in victims:
            self.remove_node(node_id)
        return len(victims)

    # -- frames ------------------------------------------------------------------------

    def add_frame(self, frame: Frame) -> Frame:
        """Añade (una copia validada de) ``frame``."""
        if frame.id in self._frames:
            raise GraphError(f"Ya existe un frame con id '{frame.id}'")
        fields = normalize_frame_fields({k: v for k, v in frame.to_dict().items() if k != "id"})
        stored = Frame(frame.id, **fields)
        self._frames[stored.id] = stored
        self._emit(GraphEvent(GraphEventKind.FRAME_ADDED, frame_id=stored.id))
        return stored

    def remove_frame(self, frame_id: str) -> Frame:
        frame = self.frame(frame_id)
        del self._frames[frame_id]
        self._emit(GraphEvent(GraphEventKind.FRAME_REMOVED, frame_id=frame_id))
        return frame

    def update_frame(self, frame_id: str, **fields: Any) -> None:
        frame = self.frame(frame_id)
        clean = normalize_frame_fields(fields)
        changed = {k: v for k, v in clean.items() if getattr(frame, k) != v}
        if changed:
            for name, value in changed.items():
                setattr(frame, name, value)
            self._emit(GraphEvent(GraphEventKind.FRAME_CHANGED, frame_id=frame_id))

    # -- general -----------------------------------------------------------------------

    def clear(self) -> None:
        self._links.clear()
        self._nodes.clear()
        self._frames.clear()
        self._emit(GraphEvent(GraphEventKind.CLEARED))
