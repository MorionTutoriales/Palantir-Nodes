"""Punto único de edición: traduce acciones del usuario en comandos de deshacer.

La escena, la vista y el panel de propiedades nunca modifican el grafo directamente;
llaman a este controlador, que valida y empuja el comando correspondiente.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QMimeData, QObject, QPointF, Signal
from PySide6.QtGui import QGuiApplication, QUndoStack

from palantir_nodes.core.errors import PalantirError
from palantir_nodes.core.graph import Frame, Graph, Link, new_id, normalize_frame_fields
from palantir_nodes.ui.editor.commands import (
    AddFrameCommand,
    AddItemsCommand,
    ConnectCommand,
    EditFramesCommand,
    MoveNodesCommand,
    RemoveItemsCommand,
    SetValueCommand,
)

if TYPE_CHECKING:
    from palantir_nodes.ui.editor.scene import NodeScene

FRAME_COLORS = ("#4A6FA5", "#5E9F6E", "#A5714A", "#8A5AA5", "#A59C4A", "#4A9FA5")
FRAME_PADDING = 30.0
FRAME_TITLE_HEIGHT = 26.0

CLIPBOARD_MIME = "application/x-palantir-nodes"
CLIPBOARD_FORMAT = "palantir-nodes/clipboard"
PASTE_OFFSET = 40.0


class EditorController(QObject):
    status_message = Signal(str)

    def __init__(self, graph: Graph, undo_stack: QUndoStack) -> None:
        super().__init__()
        self.graph = graph
        self.undo_stack = undo_stack
        self.scene: NodeScene | None = None

    # -- nodos -------------------------------------------------------------------------

    def add_node(self, type_id: str, position: QPointF | tuple[float, float]) -> str:
        definition = self.graph.registry.require(type_id)
        if isinstance(position, QPointF):
            position = (position.x(), position.y())
        data = {"id": new_id(), "type_id": type_id, "position": list(position)}
        command = AddItemsCommand(self.graph, [data], [], f"Añadir {definition.label}")
        self.undo_stack.push(command)
        self._select(command.node_ids)
        return data["id"]

    def delete_selection(self) -> None:
        if self.scene is None:
            return
        node_ids = self.scene.selected_node_ids()
        link_ids = self.scene.selected_link_ids()
        self.remove_items(node_ids, link_ids, self.scene.selected_frame_ids())

    def remove_items(
        self, node_ids: list[str], link_ids: list[str], frame_ids: list[str] | None = None
    ) -> None:
        frame_ids = frame_ids or []
        if not node_ids and not link_ids and not frame_ids:
            return
        if node_ids:
            text = f"Eliminar {len(node_ids)} nodo(s)"
        elif link_ids:
            text = f"Eliminar {len(link_ids)} conexión(es)"
        else:
            text = f"Eliminar {len(frame_ids)} frame(s)"
        self.undo_stack.push(RemoveItemsCommand(self.graph, node_ids, link_ids, text, frame_ids))

    # -- frames ------------------------------------------------------------------------

    def add_frame(
        self,
        x: float,
        y: float,
        width: float = 320.0,
        height: float = 220.0,
        title: str = "Frame",
        color: str | None = None,
    ) -> str:
        frame = Frame(
            new_id(),
            title,
            color or FRAME_COLORS[len(self.graph.frames) % len(FRAME_COLORS)],
            x,
            y,
            width,
            height,
        )
        self.undo_stack.push(AddFrameCommand(self.graph, frame))
        if self.scene is not None:
            self.scene.select_frames([frame.id])
        return frame.id

    def frame_selection(self, title: str = "Frame") -> str | None:
        """Crea un frame que envuelve los nodos seleccionados."""
        if self.scene is None:
            return None
        rect = self.scene.selected_nodes_rect()
        if rect is None:
            self.status_message.emit("Selecciona nodos para enmarcarlos")
            return None
        pad = FRAME_PADDING
        return self.add_frame(
            rect.left() - pad,
            rect.top() - pad - FRAME_TITLE_HEIGHT,
            rect.width() + 2 * pad,
            rect.height() + 2 * pad + FRAME_TITLE_HEIGHT,
            title,
        )

    def edit_frame(self, frame_id: str, **fields: Any) -> None:
        """Cambia título, color, posición o tamaño (un paso de deshacer)."""
        self.edit_frames({frame_id: fields})

    def edit_frames(
        self,
        changes: dict[str, dict[str, Any]],
        node_moves: dict[str, tuple[tuple[float, float], tuple[float, float]]] | None = None,
    ) -> None:
        frames: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        try:
            for frame_id, fields in changes.items():
                frame = self.graph.frame(frame_id)
                new = normalize_frame_fields(fields)
                old = {name: getattr(frame, name) for name in new}
                new = {k: v for k, v in new.items() if old[k] != v}
                if new:
                    frames[frame_id] = ({k: old[k] for k in new}, new)
        except PalantirError as exc:
            self.status_message.emit(str(exc))
            return
        moves = {k: v for k, v in (node_moves or {}).items() if v[0] != v[1]}
        if frames or moves:
            self.undo_stack.push(EditFramesCommand(self.graph, frames, moves))

    def move_nodes(self, moves: dict[str, tuple[tuple[float, float], tuple[float, float]]]) -> None:
        moves = {k: v for k, v in moves.items() if v[0] != v[1] and k in self.graph.nodes}
        if moves:
            self.undo_stack.push(MoveNodesCommand(self.graph, moves))

    # -- valores -----------------------------------------------------------------------

    def set_param(self, node_id: str, name: str, value: Any) -> None:
        self._set_value(node_id, name, value, "param")

    def set_input_value(self, node_id: str, name: str, value: Any) -> None:
        self._set_value(node_id, name, value, "input")

    def _set_value(self, node_id: str, name: str, value: Any, target: str) -> None:
        node = self.graph.node(node_id)
        definition = node.definition
        try:
            if target == "param":
                spec = definition.param(name)
                old = node.params[name]
            else:
                spec = definition.input(name).value_spec()
                old = node.input_values[name]
            new = spec.coerce(value)
        except PalantirError as exc:
            self.status_message.emit(str(exc))
            return
        if new != old:
            self.undo_stack.push(SetValueCommand(self.graph, node_id, name, old, new, target))

    # -- conexiones --------------------------------------------------------------------

    def connect(
        self,
        src_node: str,
        src_socket: str,
        dst_node: str,
        dst_socket: str,
        *,
        remove_link_ids: list[str] | None = None,
    ) -> bool:
        check = self.graph.can_connect(src_node, src_socket, dst_node, dst_socket)
        if not check:
            self.status_message.emit(f"Conexión no válida: {check.reason}")
            return False
        self.undo_stack.push(
            ConnectCommand(
                self.graph,
                src_node,
                src_socket,
                dst_node,
                dst_socket,
                link_id=new_id(),
                remove_link_ids=remove_link_ids,
            )
        )
        if check.conversion:
            self.status_message.emit(f"Conectado con conversión implícita: {check.conversion}")
        return True

    # -- portapapeles ------------------------------------------------------------------

    def serialize_nodes(self, node_ids: list[str]) -> dict[str, Any]:
        ids = set(node_ids)
        nodes = [self.graph.node(i).to_dict() for i in node_ids]
        links = [
            link.to_dict()
            for link in self.graph.links.values()
            if link.src_node in ids and link.dst_node in ids
        ]
        return {"format": CLIPBOARD_FORMAT, "version": 1, "nodes": nodes, "links": links}

    def copy_selection(self) -> int:
        if self.scene is None:
            return 0
        node_ids = self.scene.selected_node_ids()
        if not node_ids:
            return 0
        payload = json.dumps(self.serialize_nodes(node_ids))
        mime = QMimeData()
        mime.setData(CLIPBOARD_MIME, payload.encode("utf-8"))
        mime.setText(payload)
        QGuiApplication.clipboard().setMimeData(mime)
        self.status_message.emit(f"{len(node_ids)} nodo(s) copiados")
        return len(node_ids)

    def paste(self, at: QPointF | None = None) -> list[str]:
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None:
            return []
        if mime.hasFormat(CLIPBOARD_MIME):
            raw = bytes(mime.data(CLIPBOARD_MIME)).decode("utf-8")
        elif mime.hasText():
            raw = mime.text()
        else:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict) or payload.get("format") != CLIPBOARD_FORMAT:
            return []
        return self.insert_payload(payload, at, "Pegar")

    def duplicate_selection(self) -> list[str]:
        if self.scene is None:
            return []
        node_ids = self.scene.selected_node_ids()
        if not node_ids:
            return []
        return self.insert_payload(self.serialize_nodes(node_ids), None, "Duplicar")

    def insert_payload(self, payload: dict[str, Any], at: QPointF | None, text: str) -> list[str]:
        """Inserta nodos serializados con ids nuevos.

        Con ``at`` el conjunto se centra en ese punto; sin él se desplaza un poco respecto
        al original. Los tipos desconocidos se omiten y se informa.
        """
        raw_nodes = [n for n in payload.get("nodes", []) if isinstance(n, dict)]
        known = [clean for n in raw_nodes if (clean := self._sanitize_node(n)) is not None]
        skipped = len(raw_nodes) - len(known)
        if not known:
            if skipped:
                self.status_message.emit(f"Se omitieron {skipped} nodo(s) de tipo desconocido")
            return []

        xs = [float(n["position"][0]) for n in known]
        ys = [float(n["position"][1]) for n in known]
        if at is not None:
            dx = at.x() - (min(xs) + max(xs)) / 2
            dy = at.y() - (min(ys) + max(ys)) / 2
        else:
            dx = dy = PASTE_OFFSET

        id_map: dict[str, str] = {}
        nodes = []
        for n in known:
            id_map[n["id"]] = new_id()
            nodes.append(
                {
                    **n,
                    "id": id_map[n["id"]],
                    "position": [float(n["position"][0]) + dx, float(n["position"][1]) + dy],
                }
            )
        links = []
        for raw in payload.get("links", []):
            try:
                link = Link.from_dict(raw)
            except (KeyError, TypeError):
                continue
            if link.src_node in id_map and link.dst_node in id_map:
                links.append(
                    Link(
                        new_id(),
                        id_map[link.src_node],
                        link.src_socket,
                        id_map[link.dst_node],
                        link.dst_socket,
                    )
                )

        command = AddItemsCommand(self.graph, nodes, links, f"{text} {len(nodes)} nodo(s)")
        self.undo_stack.push(command)
        self._select(command.node_ids)
        if skipped:
            self.status_message.emit(f"Se omitieron {skipped} nodo(s) de tipo desconocido")
        return command.node_ids

    def _sanitize_node(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Valida un nodo serializado; descarta valores inválidos. ``None`` si es inservible."""
        definition = self.graph.registry.get(data.get("type_id", ""))
        if definition is None or "id" not in data:
            return None
        try:
            x, y = (float(c) for c in data.get("position", (0.0, 0.0)))
        except (TypeError, ValueError):
            return None

        def valid(values: Any, spec_for) -> dict[str, Any]:
            result = {}
            for name, value in (values if isinstance(values, dict) else {}).items():
                spec = spec_for(name)
                if spec is None:
                    continue
                try:
                    result[name] = spec.coerce(value)
                except PalantirError:
                    continue
            return result

        def input_spec(name: str):
            spec = definition.input(name)
            return spec.value_spec() if spec else None

        return {
            "id": str(data["id"]),
            "type_id": definition.type_id,
            "position": [x, y],
            "params": valid(data.get("params"), definition.param),
            "input_values": valid(data.get("input_values"), input_spec),
        }

    # -- general -----------------------------------------------------------------------

    def new_graph(self) -> None:
        self.graph.clear()
        self.undo_stack.clear()

    def _select(self, node_ids: list[str]) -> None:
        if self.scene is not None:
            self.scene.select_nodes(node_ids)
