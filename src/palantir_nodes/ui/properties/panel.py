"""Panel de propiedades: edita parámetros y valores de entradas del nodo seleccionado."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.core.graph import Graph, GraphEvent, GraphEventKind
from palantir_nodes.nodes.categories import get_category
from palantir_nodes.ui.editor.controller import EditorController
from palantir_nodes.ui.panels import EmptyState
from palantir_nodes.ui.properties.widgets import ValueWidget, create_value_widget
from palantir_nodes.ui.theme import Colors


class PropertiesPanel(QWidget):
    def __init__(self, graph: Graph, controller: EditorController, parent=None) -> None:
        super().__init__(parent)
        self.graph = graph
        self.controller = controller
        self.node_id: str | None = None
        self.frame_id: str | None = None
        self._param_widgets: dict[str, ValueWidget] = {}
        self._input_widgets: dict[str, ValueWidget] = {}
        self._input_labels: dict[str, QLabel] = {}
        self._statuses: dict[str, tuple[str, str]] = {}
        self._status_label: QLabel | None = None

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        graph.subscribe(self._on_graph_event)
        self.show_selection([])

    # -- contenido ---------------------------------------------------------------------

    def show_frame(self, frame_id: str) -> None:
        """Propiedades de un frame: título, color y geometría."""
        self.node_id = None
        self.frame_id = frame_id
        self._param_widgets.clear()
        self._input_widgets.clear()
        self._input_labels.clear()
        self._status_label = None
        frame = self.graph.frame(frame_id)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self._scroll.setWidget(content)

        title = QLabel("Frame")
        title.setStyleSheet(
            f"font-size: 11pt; font-weight: bold; padding-left: 6px;"
            f"border-left: 4px solid {frame.color};"
        )
        layout.addWidget(title)
        hint = QLabel(
            "Agrupa nodos visualmente. Arrastra su título para moverlo junto con los nodos "
            "que contiene y su esquina inferior derecha para redimensionarlo."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        layout.addWidget(hint)

        box = QGroupBox("Frame")
        form = QFormLayout(box)
        self._frame_title = QLineEdit(frame.title)
        self._frame_title.editingFinished.connect(
            lambda: self.controller.edit_frame(frame_id, title=self._frame_title.text())
        )
        form.addRow("Título", self._frame_title)
        self._frame_color = QPushButton()
        self._frame_color.clicked.connect(lambda: self._pick_frame_color(frame_id))
        form.addRow("Color", self._frame_color)
        self._frame_info = QLabel()
        form.addRow("Geometría", self._frame_info)
        layout.addWidget(box)
        layout.addStretch(1)
        self._refresh_frame_widgets(frame_id)

    def _refresh_frame_widgets(self, frame_id: str) -> None:
        frame = self.graph.frame(frame_id)
        if self._frame_title.text() != frame.title and not self._frame_title.hasFocus():
            self._frame_title.setText(frame.title)
        self._frame_color.setText(frame.color)
        self._frame_color.setStyleSheet(
            f"QPushButton {{ background: {frame.color}; border: 1px solid #111; color: #FFF; }}"
        )
        self._frame_info.setText(
            f"{frame.width:.0f} × {frame.height:.0f} en ({frame.x:.0f}, {frame.y:.0f})"
        )

    def _pick_frame_color(self, frame_id: str) -> None:
        color = QColorDialog.getColor(QColor(self.graph.frame(frame_id).color), self)
        if color.isValid():
            self.controller.edit_frame(frame_id, color=color.name())

    def show_selection(self, node_ids: list[str]) -> None:
        self.frame_id = None
        self.node_id = node_ids[0] if len(node_ids) == 1 else None
        self._param_widgets.clear()
        self._input_widgets.clear()
        self._input_labels.clear()
        self._status_label = None

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self._scroll.setWidget(content)

        if self.node_id is None:
            if node_ids:
                empty = EmptyState(
                    "layers",
                    f"{len(node_ids)} nodos seleccionados.\nSelecciona uno solo para editarlo.",
                )
            else:
                empty = EmptyState(
                    "sliders-horizontal", "Selecciona un nodo para ver sus propiedades."
                )
            layout.addWidget(empty, 1)
            return

        node = self.graph.node(self.node_id)
        definition = node.definition
        color = get_category(definition.category).color
        title = QLabel(definition.label)
        title.setStyleSheet(
            f"font-size: 11pt; font-weight: bold; padding-left: 6px;border-left: 4px solid {color};"
        )
        layout.addWidget(title)
        meta = QLabel(f"{definition.category} · {definition.type_id}")
        meta.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        layout.addWidget(meta)
        if definition.description:
            desc = QLabel(definition.description)
            desc.setWordWrap(True)
            layout.addWidget(desc)
        if not definition.is_implemented():
            pending = QLabel("Este nodo todavía no tiene procesamiento implementado.")
            pending.setWordWrap(True)
            pending.setStyleSheet("color: #D9A441;")
            layout.addWidget(pending)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)
        self._refresh_status()

        if definition.params:
            box = QGroupBox("Parámetros")
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            for spec in definition.params:
                widget = create_value_widget(spec, node.params[spec.name])
                widget.value_changed.connect(
                    lambda v, n=spec.name: self.controller.set_param(self.node_id, n, v)
                )
                form.addRow(spec.display_label, widget)
                self._param_widgets[spec.name] = widget
            layout.addWidget(box)

        editable = [s for s in definition.inputs if s.has_default]
        if editable:
            box = QGroupBox("Entradas")
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            for spec in editable:
                widget = create_value_widget(spec.value_spec(), node.input_values[spec.name])
                widget.value_changed.connect(
                    lambda v, n=spec.name: self.controller.set_input_value(self.node_id, n, v)
                )
                label = QLabel(spec.display_label)
                form.addRow(label, widget)
                self._input_widgets[spec.name] = widget
                self._input_labels[spec.name] = label
            layout.addWidget(box)
            self._refresh_connected()

        sockets = QGroupBox("Sockets")
        form = QFormLayout(sockets)
        for spec in definition.inputs:
            form.addRow(self._socket_label(spec.display_label, spec.type), QLabel("entrada"))
        for param in definition.connectable_params():
            form.addRow(
                self._socket_label(param.display_label, param.socket_type),
                QLabel("entrada (parámetro)"),
            )
        for spec in definition.outputs:
            form.addRow(self._socket_label(spec.display_label, spec.type), QLabel("salida"))
        layout.addWidget(sockets)
        layout.addStretch(1)
        self._refresh_connected()

    @staticmethod
    def _socket_label(label: str, socket_type) -> QLabel:
        widget = QLabel(
            f"<span style='color:{socket_type.color}'>●</span> {label} "
            f"<span style='color:{Colors.TEXT_DIM}'>({socket_type.value})</span>"
        )
        widget.setTextFormat(Qt.TextFormat.RichText)
        return widget

    def set_statuses(self, errors: dict[str, str], blocked: dict[str, str]) -> None:
        """Errores de la última ejecución; actualiza sin reconstruir el panel (no roba el foco)."""
        self._statuses = {n: ("error", m) for n, m in errors.items()}
        self._statuses.update({n: ("blocked", m) for n, m in blocked.items()})
        self._refresh_status()

    def _refresh_status(self) -> None:
        label = self._status_label
        if label is None:
            return
        kind, message = self._statuses.get(self.node_id, ("", ""))
        if not kind:
            label.hide()
            return
        color = Colors.LINK_INVALID if kind == "error" else "#D9A441"
        title = "Error" if kind == "error" else "Bloqueado"
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(f"<b>{title}:</b> {html.escape(message)}")
        label.setStyleSheet(f"color: {color};")
        label.show()

    def _refresh_connected(self) -> None:
        if self.node_id is None:
            return
        connected = self.graph.connected_inputs(self.node_id)
        for name, widget in (*self._input_widgets.items(), *self._param_widgets.items()):
            is_connected = name in connected
            widget.setEnabled(not is_connected)
            if is_connected:
                widget.setToolTip("Conectado: el valor proviene de otro nodo")
            else:
                spec = getattr(widget, "spec", None)
                widget.setToolTip(spec.tooltip if spec is not None else "")

    # -- eventos del grafo -------------------------------------------------------------

    def _on_graph_event(self, event: GraphEvent) -> None:
        if event.kind in (GraphEventKind.CLEARED, GraphEventKind.REBUILT):
            self.show_selection([])
            return
        if event.kind in (GraphEventKind.FRAME_CHANGED, GraphEventKind.FRAME_REMOVED):
            if self.frame_id is not None and event.frame_id == self.frame_id:
                if event.kind is GraphEventKind.FRAME_REMOVED:
                    self.show_selection([])
                else:
                    self._refresh_frame_widgets(self.frame_id)
            return
        if self.node_id is None or event.node_id != self.node_id:
            return
        if event.kind is GraphEventKind.NODE_REMOVED:
            self.show_selection([])
        elif event.kind is GraphEventKind.PARAM_CHANGED:
            widget = self._param_widgets.get(event.name)
            if widget is not None:
                widget.set_value(self.graph.node(self.node_id).params[event.name])
        elif event.kind is GraphEventKind.INPUT_VALUE_CHANGED:
            widget = self._input_widgets.get(event.name)
            if widget is not None:
                widget.set_value(self.graph.node(self.node_id).input_values[event.name])
        elif event.kind in (GraphEventKind.LINK_ADDED, GraphEventKind.LINK_REMOVED):
            self._refresh_connected()
