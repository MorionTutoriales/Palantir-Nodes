"""Modelo lógico del grafo: nodos, conexiones y eventos de cambio."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from palantir_nodes.core.errors import ConnectionRejectedError, GraphError
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


class GraphEventKind(Enum):
    NODE_ADDED = auto()
    NODE_REMOVED = auto()
    NODE_MOVED = auto()
    PARAM_CHANGED = auto()
    INPUT_VALUE_CHANGED = auto()
    LINK_ADDED = auto()
    LINK_REMOVED = auto()
    CLEARED = auto()


@dataclass(frozen=True)
class GraphEvent:
    kind: GraphEventKind
    node_id: str | None = None
    link: Link | None = None
    name: str | None = None


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

    # -- general -----------------------------------------------------------------------

    def clear(self) -> None:
        self._links.clear()
        self._nodes.clear()
        self._emit(GraphEvent(GraphEventKind.CLEARED))
