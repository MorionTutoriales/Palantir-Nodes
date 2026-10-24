"""Comandos de deshacer/rehacer. Cada uno modifica el grafo lógico, nunca la escena.

La escena se actualiza sola a partir de los eventos del grafo, así que deshacer y
rehacer funcionan igual sin importar desde dónde se originó el cambio.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtGui import QUndoCommand

from palantir_nodes.core.errors import GraphError
from palantir_nodes.core.graph import Frame, Graph, Link

_MERGE_ID_SET_VALUE = 1001
_MERGE_WINDOW_SECONDS = 1.5


class AddItemsCommand(QUndoCommand):
    """Añade nodos (como diccionarios ``NodeInstance.to_dict``) y conexiones."""

    def __init__(
        self, graph: Graph, nodes: list[dict[str, Any]], links: list[Link], text: str
    ) -> None:
        super().__init__(text)
        self._graph = graph
        self._nodes = nodes
        self._links = links

    @property
    def node_ids(self) -> list[str]:
        return [n["id"] for n in self._nodes]

    def redo(self) -> None:
        for i, data in enumerate(self._nodes):
            node = self._graph.add_node_from_dict(data)
            self._nodes[i] = node.to_dict()  # guarda los valores por defecto aplicados
        # Conexiones inválidas (p. ej. un portapapeles manipulado) se descartan para no
        # dejar el comando a medias.
        valid = []
        for link in self._links:
            try:
                self._graph.add_link_object(link)
                valid.append(link)
            except GraphError:
                continue
        self._links = valid

    def undo(self) -> None:
        for link in reversed(self._links):
            if link.id in self._graph.links:
                self._graph.remove_link(link.id)
        for data in reversed(self._nodes):
            self._graph.remove_node(data["id"])


class RemoveItemsCommand(QUndoCommand):
    """Elimina nodos (con todas sus conexiones), conexiones sueltas y frames."""

    def __init__(
        self,
        graph: Graph,
        node_ids: list[str],
        link_ids: list[str],
        text: str,
        frame_ids: list[str] | None = None,
    ) -> None:
        super().__init__(text)
        self._graph = graph
        self._node_ids = list(node_ids)
        self._link_ids = list(link_ids)
        self._frame_ids = list(frame_ids or [])
        self._nodes: list[dict[str, Any]] = []
        self._links: list[Link] = []
        self._frames: list[Frame] = []

    def redo(self) -> None:
        self._frames = [self._graph.frame(i).copy() for i in self._frame_ids]
        for frame_id in self._frame_ids:
            self._graph.remove_frame(frame_id)
        wanted = set(self._link_ids)
        for node_id in self._node_ids:
            wanted.update(link.id for link in self._graph.links_of_node(node_id))
        self._links = [link for link in self._graph.links.values() if link.id in wanted]
        self._nodes = [self._graph.node(node_id).to_dict() for node_id in self._node_ids]
        for link in self._links:
            self._graph.remove_link(link.id)
        for node_id in self._node_ids:
            self._graph.remove_node(node_id)

    def undo(self) -> None:
        for data in self._nodes:
            self._graph.add_node_from_dict(data)
        for link in self._links:
            self._graph.add_link_object(link)
        for frame in self._frames:
            self._graph.add_frame(frame)


class AddFrameCommand(QUndoCommand):
    def __init__(self, graph: Graph, frame: Frame, text: str = "Añadir frame") -> None:
        super().__init__(text)
        self._graph = graph
        self._frame = frame.copy()

    def redo(self) -> None:
        self._graph.add_frame(self._frame)

    def undo(self) -> None:
        self._graph.remove_frame(self._frame.id)


class EditFramesCommand(QUndoCommand):
    """Cambia campos de uno o varios frames y, a la vez, mueve nodos (al arrastrar un frame
    los nodos que contiene lo acompañan, y todo se deshace como un solo paso)."""

    def __init__(
        self,
        graph: Graph,
        frames: dict[str, tuple[dict[str, Any], dict[str, Any]]],
        node_moves: dict[str, tuple[tuple[float, float], tuple[float, float]]] | None = None,
        text: str = "Editar frame",
    ) -> None:
        super().__init__(text)
        self._graph = graph
        self._frames = frames  # id -> (campos antes, campos después)
        self._node_moves = node_moves or {}

    def redo(self) -> None:
        for frame_id, (_, new) in self._frames.items():
            self._graph.update_frame(frame_id, **new)
        for node_id, (_, new_pos) in self._node_moves.items():
            self._graph.move_node(node_id, new_pos)

    def undo(self) -> None:
        for frame_id, (old, _) in self._frames.items():
            self._graph.update_frame(frame_id, **old)
        for node_id, (old_pos, _) in self._node_moves.items():
            self._graph.move_node(node_id, old_pos)


class MoveNodesCommand(QUndoCommand):
    def __init__(
        self,
        graph: Graph,
        moves: dict[str, tuple[tuple[float, float], tuple[float, float]]],
        text: str = "Mover nodos",
    ) -> None:
        super().__init__(text)
        self._graph = graph
        self._moves = moves

    def redo(self) -> None:
        for node_id, (_, new) in self._moves.items():
            self._graph.move_node(node_id, new)

    def undo(self) -> None:
        for node_id, (old, _) in self._moves.items():
            self._graph.move_node(node_id, old)


class ConnectCommand(QUndoCommand):
    """Crea una conexión. Reemplaza la que ya ocupe la entrada destino y, opcionalmente,
    elimina otras (p. ej. la conexión que se arrastró fuera de una entrada)."""

    def __init__(
        self,
        graph: Graph,
        src_node: str,
        src_socket: str,
        dst_node: str,
        dst_socket: str,
        *,
        link_id: str,
        remove_link_ids: list[str] | None = None,
    ) -> None:
        super().__init__("Conectar")
        self._graph = graph
        self._link = Link(link_id, src_node, src_socket, dst_node, dst_socket)
        self._remove_ids = list(remove_link_ids or [])
        self._removed: list[Link] = []

    def redo(self) -> None:
        to_remove = [self._graph.links[i] for i in self._remove_ids if i in self._graph.links]
        occupying = self._graph.link_to_input(self._link.dst_node, self._link.dst_socket)
        if occupying is not None and occupying not in to_remove:
            to_remove.append(occupying)
        self._removed = [self._graph.remove_link(link.id) for link in to_remove]
        try:
            self._graph.add_link_object(self._link)
        except Exception:
            for link in self._removed:
                self._graph.add_link_object(link)
            self._removed = []
            raise

    def undo(self) -> None:
        self._graph.remove_link(self._link.id)
        for link in reversed(self._removed):
            self._graph.add_link_object(link)


class SetValueCommand(QUndoCommand):
    """Cambia un parámetro (``target="param"``) o el valor de una entrada sin conectar
    (``target="input"``). Cambios seguidos del mismo valor se fusionan en un paso."""

    def __init__(
        self, graph: Graph, node_id: str, name: str, old: Any, new: Any, target: str = "param"
    ) -> None:
        super().__init__(f"Cambiar {name}")
        self._graph = graph
        self.node_id = node_id
        self.name = name
        self.target = target
        self._old = old
        self._new = new
        self._stamp = time.monotonic()

    def _apply(self, value: Any) -> None:
        if self.target == "param":
            self._graph.set_param(self.node_id, self.name, value)
        else:
            self._graph.set_input_value(self.node_id, self.name, value)

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)

    def id(self) -> int:
        return _MERGE_ID_SET_VALUE

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, SetValueCommand):
            return False
        same_target = (other.node_id, other.name, other.target) == (
            self.node_id,
            self.name,
            self.target,
        )
        if not same_target or other._stamp - self._stamp > _MERGE_WINDOW_SECONDS:
            return False
        self._new = other._new
        self._stamp = other._stamp
        return True
