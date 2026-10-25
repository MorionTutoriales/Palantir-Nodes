"""Escena del editor: refleja el grafo lógico y gestiona el arrastre de conexiones."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent

from palantir_nodes.core.graph import Frame, Graph, GraphEvent, GraphEventKind, Link, NodeInstance
from palantir_nodes.core.validation import ConnectionCheck, Endpoint, check_endpoints
from palantir_nodes.ui.editor.controller import EditorController
from palantir_nodes.ui.editor.frame_item import FrameItem
from palantir_nodes.ui.editor.link_item import DragLinkItem, LinkItem
from palantir_nodes.ui.editor.node_item import NodeItem
from palantir_nodes.ui.editor.socket_item import SocketItem
from palantir_nodes.ui.theme import Colors

SCENE_EXTENT = 50_000.0


@dataclass
class _LinkDrag:
    origin: SocketItem  # extremo fijo
    item: DragLinkItem
    detached: Link | None = None  # conexión levantada desde una entrada
    target: SocketItem | None = None
    check: ConnectionCheck | None = None
    src: Endpoint | None = None
    dst: Endpoint | None = None


class NodeScene(QGraphicsScene):
    status_message = Signal(str)
    frame_rename_requested = Signal(str)
    # Se soltó una conexión nueva en un espacio vacío: (nodo, socket, ¿es salida?, posición).
    link_dropped = Signal(str, str, bool, QPointF)
    # (nodo, "param" | "input", nombre, rectángulo del campo en la escena)
    field_edit_requested = Signal(str, str, str, QRectF)

    def __init__(self, graph: Graph, controller: EditorController, parent=None) -> None:
        super().__init__(parent)
        self.setSceneRect(-SCENE_EXTENT / 2, -SCENE_EXTENT / 2, SCENE_EXTENT, SCENE_EXTENT)
        self.graph = graph
        self.controller = controller
        controller.scene = self
        self.node_items: dict[str, NodeItem] = {}
        self.link_items: dict[str, LinkItem] = {}
        self.frame_items: dict[str, FrameItem] = {}
        self.suppress_node_moves = False  # lo activa un frame mientras arrastra sus nodos
        self._links_by_node: dict[str, set[str]] = {}
        self._drag: _LinkDrag | None = None
        self._press_positions: dict[str, tuple[float, float]] = {}
        graph.subscribe(self._on_graph_event)
        self._rebuild()

    # -- sincronización con el grafo ---------------------------------------------------

    def _rebuild(self) -> None:
        self.cancel_link_drag()
        for item in list(self.link_items.values()):
            self.removeItem(item)
        for item in list(self.node_items.values()):
            self.removeItem(item)
        for item in list(self.frame_items.values()):
            self.removeItem(item)
        self.node_items.clear()
        self.link_items.clear()
        self.frame_items.clear()
        self._links_by_node.clear()
        for frame in self.graph.frames.values():
            self._add_frame_item(frame)
        for node in self.graph.nodes.values():
            self._add_node_item(node)
        for link in self.graph.links.values():
            self._add_link_item(link)

    def _on_graph_event(self, event: GraphEvent) -> None:
        kind = event.kind
        if kind is GraphEventKind.NODE_ADDED:
            self._add_node_item(self.graph.node(event.node_id))
        elif kind is GraphEventKind.NODE_REMOVED:
            self._remove_node_item(event.node_id)
        elif kind is GraphEventKind.NODE_MOVED:
            item = self.node_items.get(event.node_id)
            if item is not None:
                x, y = self.graph.node(event.node_id).position
                if item.scene_position() != (x, y):
                    item.setPos(x, y)
        elif kind in (GraphEventKind.PARAM_CHANGED, GraphEventKind.INPUT_VALUE_CHANGED):
            item = self.node_items.get(event.node_id)
            if item is not None:
                item.refresh()
        elif kind is GraphEventKind.LINK_ADDED:
            self._add_link_item(event.link)
        elif kind is GraphEventKind.LINK_REMOVED:
            self._remove_link_item(event.link)
        elif kind is GraphEventKind.FRAME_ADDED:
            self._add_frame_item(self.graph.frame(event.frame_id))
        elif kind is GraphEventKind.FRAME_REMOVED:
            item = self.frame_items.pop(event.frame_id, None)
            if item is not None:
                self.removeItem(item)
        elif kind is GraphEventKind.FRAME_CHANGED:
            item = self.frame_items.get(event.frame_id)
            if item is not None:
                item.sync(self.graph.frame(event.frame_id))
        elif kind in (GraphEventKind.CLEARED, GraphEventKind.REBUILT):
            self._rebuild()

    def _add_frame_item(self, frame: Frame) -> None:
        item = FrameItem(frame)
        self.addItem(item)
        self.frame_items[frame.id] = item

    def _add_node_item(self, node: NodeInstance) -> None:
        item = NodeItem(node)
        item.setPos(*node.position)
        self.addItem(item)
        self.node_items[node.id] = item
        self._links_by_node.setdefault(node.id, set())

    def _remove_node_item(self, node_id: str) -> None:
        if self._drag is not None and self._drag.origin.node_id == node_id:
            self.cancel_link_drag()
        item = self.node_items.pop(node_id, None)
        if item is not None:
            self.removeItem(item)
        self._links_by_node.pop(node_id, None)

    def _add_link_item(self, link: Link) -> None:
        src = self.node_items[link.src_node].socket(link.src_socket, is_output=True)
        dst = self.node_items[link.dst_node].socket(link.dst_socket, is_output=False)
        item = LinkItem(link, src, dst)
        self.addItem(item)
        self.link_items[link.id] = item
        self._links_by_node.setdefault(link.src_node, set()).add(link.id)
        self._links_by_node.setdefault(link.dst_node, set()).add(link.id)
        self._refresh_connected(link.dst_node)

    def _remove_link_item(self, link: Link) -> None:
        item = self.link_items.pop(link.id, None)
        if item is not None:
            self.removeItem(item)
        for node_id in (link.src_node, link.dst_node):
            self._links_by_node.get(node_id, set()).discard(link.id)
        self._refresh_connected(link.dst_node)

    def _refresh_connected(self, node_id: str) -> None:
        item = self.node_items.get(node_id)
        if item is not None:
            item.set_connected_inputs(self.graph.connected_inputs(node_id))

    def apply_previews(self, previews: dict[str, np.ndarray]) -> None:
        """Muestra la miniatura de cada nodo (y quita la de los que ya no tienen imagen)."""
        for node_id, item in self.node_items.items():
            item.set_preview(previews.get(node_id))

    def apply_statuses(self, errors: dict[str, str], blocked: dict[str, str]) -> None:
        for node_id, item in self.node_items.items():
            if node_id in errors:
                item.set_status("error", errors[node_id])
            elif node_id in blocked:
                item.set_status("blocked", blocked[node_id])
            else:
                item.set_status(None)

    def node_item_moved(self, node_id: str) -> None:
        for link_id in self._links_by_node.get(node_id, ()):
            item = self.link_items.get(link_id)
            if item is not None:
                item.update_path()

    # -- selección ---------------------------------------------------------------------

    def selected_node_ids(self) -> list[str]:
        return [i.node_id for i in self.selectedItems() if isinstance(i, NodeItem)]

    def selected_link_ids(self) -> list[str]:
        return [i.link_id for i in self.selectedItems() if isinstance(i, LinkItem)]

    def selected_frame_ids(self) -> list[str]:
        return [i.frame_id for i in self.selectedItems() if isinstance(i, FrameItem)]

    def selected_nodes_rect(self) -> QRectF | None:
        """Rectángulo que envuelve los nodos seleccionados (``None`` si no hay)."""
        rect: QRectF | None = None
        for item in self.selectedItems():
            if isinstance(item, NodeItem):
                bounds = item.sceneBoundingRect()
                rect = bounds if rect is None else rect.united(bounds)
        return rect

    def select_nodes(self, node_ids: list[str]) -> None:
        self.clearSelection()
        for node_id in node_ids:
            item = self.node_items.get(node_id)
            if item is not None:
                item.setSelected(True)

    def select_frames(self, frame_ids: list[str]) -> None:
        self.clearSelection()
        for frame_id in frame_ids:
            item = self.frame_items.get(frame_id)
            if item is not None:
                item.setSelected(True)

    # -- ratón -------------------------------------------------------------------------

    def socket_at(self, pos: QPointF) -> SocketItem | None:
        for item in self.items(pos):
            if isinstance(item, SocketItem):
                return item
        return None

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag is not None:
            # Cualquier otro botón durante el arrastre lo cancela (como en Blender).
            self.cancel_link_drag()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            socket = self.socket_at(event.scenePos())
            if socket is not None:
                self._begin_link_drag(socket, event.scenePos())
                event.accept()
                return
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_positions = {
                i.node_id: i.scene_position()
                for i in self.selectedItems()
                if isinstance(i, NodeItem)
            }

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag is not None:
            self._update_link_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._finish_link_drag(event.scenePos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.suppress_node_moves:
            # Un frame acaba de registrar el movimiento (y el de los nodos que contiene).
            self.suppress_node_moves = False
            self._press_positions = {}
            return
        if event.button() == Qt.MouseButton.LeftButton and self._press_positions:
            moves = {}
            for node_id, old in self._press_positions.items():
                item = self.node_items.get(node_id)
                if item is not None and item.scene_position() != old:
                    moves[node_id] = (old, item.scene_position())
            self._press_positions = {}
            self.controller.move_nodes(moves)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self.cancel_link_drag()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- arrastre de conexiones --------------------------------------------------------

    @property
    def is_dragging_link(self) -> bool:
        return self._drag is not None

    def _begin_link_drag(self, socket: SocketItem, pos: QPointF) -> None:
        detached = None
        origin = socket
        if not socket.is_output:
            detached = self.graph.link_to_input(socket.node_id, socket.name)
            if detached is not None:
                # Levantar la conexión existente: el extremo fijo pasa a ser su salida.
                origin = self.node_items[detached.src_node].socket(detached.src_socket, True)
                self.link_items[detached.id].setVisible(False)
        item = DragLinkItem()
        self.addItem(item)
        self._drag = _LinkDrag(origin=origin, item=item, detached=detached)
        self._update_link_drag(pos)

    def _update_link_drag(self, pos: QPointF) -> None:
        drag = self._drag
        target = self.socket_at(pos)
        if target is drag.origin:
            target = None
        if drag.target is not None and drag.target is not target:
            drag.target.set_highlight(None)
        drag.target = target
        drag.check = drag.src = drag.dst = None

        end = pos
        if target is not None:
            end = target.center()
            a = Endpoint(drag.origin.node_id, drag.origin.name, drag.origin.is_output)
            b = Endpoint(target.node_id, target.name, target.is_output)
            check, src, dst = check_endpoints(self.graph, a, b)
            if (
                not check
                and drag.detached is not None
                and src is not None
                and (dst.node_id, dst.socket) == (drag.detached.dst_node, drag.detached.dst_socket)
            ):
                check = ConnectionCheck(True)  # soltar la conexión donde estaba
            drag.check, drag.src, drag.dst = check, src, dst
            color = Colors.LINK_VALID if check else Colors.LINK_INVALID
            target.set_highlight(QColor(color))
            drag.item.set_state(color, dashed=False)
            if check:
                extra = f" (conversión {check.conversion})" if check.conversion else ""
                self.status_message.emit(f"Conexión válida{extra}")
            else:
                self.status_message.emit(f"Conexión no válida: {check.reason}")
        else:
            drag.item.set_state(Colors.LINK_NEUTRAL, dashed=True)

        start = drag.origin.center()
        if drag.origin.is_output:
            drag.item.set_bezier(start, end)
        else:
            drag.item.set_bezier(end, start)

    def _is_empty_space(self, pos: QPointF) -> bool:
        """``True`` si no hay ningún nodo bajo ``pos`` (conexiones y frames no cuentan)."""
        return not any(isinstance(item, NodeItem) for item in self.items(pos))

    def _finish_link_drag(self, pos: QPointF) -> None:
        drag = self._drag
        detached = drag.detached
        self._end_drag_visuals()

        if drag.target is None:
            if detached is not None:
                self.controller.remove_items([], [detached.id])
            elif self._is_empty_space(pos):
                origin = drag.origin
                self.link_dropped.emit(origin.node_id, origin.name, origin.is_output, pos)
            else:
                self.status_message.emit("Suelta sobre un socket o en un espacio vacío")
            return
        if not drag.check:
            self.status_message.emit(f"Conexión no válida: {drag.check.reason}")
            return
        src, dst = drag.src, drag.dst
        if detached is not None and (
            detached.src_node,
            detached.src_socket,
            detached.dst_node,
            detached.dst_socket,
        ) == (src.node_id, src.socket, dst.node_id, dst.socket):
            return  # sin cambios
        self.controller.connect(
            src.node_id,
            src.socket,
            dst.node_id,
            dst.socket,
            remove_link_ids=[detached.id] if detached is not None else None,
        )

    def _end_drag_visuals(self) -> None:
        drag = self._drag
        self._drag = None
        if drag is None:
            return
        if drag.target is not None:
            drag.target.set_highlight(None)
        self.removeItem(drag.item)
        if drag.detached is not None and drag.detached.id in self.link_items:
            self.link_items[drag.detached.id].setVisible(True)

    def cancel_link_drag(self) -> None:
        if self._drag is not None:
            self._end_drag_visuals()
            self.status_message.emit("Conexión cancelada")
