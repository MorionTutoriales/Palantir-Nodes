"""Panel de propiedades: edita parámetros y valores de entradas del nodo seleccionado."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.core.graph import Graph, GraphEvent, GraphEventKind
from palantir_nodes.nodes.categories import get_category
from palantir_nodes.ui.editor.controller import EditorController
from palantir_nodes.ui.properties.widgets import ValueWidget, create_value_widget
from palantir_nodes.ui.theme import Colors


class PropertiesPanel(QWidget):
    def __init__(self, graph: Graph, controller: EditorController, parent=None) -> None:
        super().__init__(parent)
        self.graph = graph
        self.controller = controller
        self.node_id: str | None = None
        self._param_widgets: dict[str, ValueWidget] = {}
        self._input_widgets: dict[str, ValueWidget] = {}
        self._input_labels: dict[str, QLabel] = {}

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        graph.subscribe(self._on_graph_event)
        self.show_selection([])

    # -- contenido ---------------------------------------------------------------------

    def show_selection(self, node_ids: list[str]) -> None:
        self.node_id = node_ids[0] if len(node_ids) == 1 else None
        self._param_widgets.clear()
        self._input_widgets.clear()
        self._input_labels.clear()

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self._scroll.setWidget(content)

        if self.node_id is None:
            text = (
                f"{len(node_ids)} nodos seleccionados.\nSelecciona uno solo para editarlo."
                if node_ids
                else "Selecciona un nodo para ver sus propiedades."
            )
            hint = QLabel(text)
            hint.setStyleSheet(f"color: {Colors.TEXT_DIM};")
            hint.setWordWrap(True)
            layout.addWidget(hint)
            layout.addStretch(1)
            return

        node = self.graph.node(self.node_id)
        definition = node.definition
        color = get_category(definition.category).color
        title = QLabel(definition.label)
        title.setStyleSheet(
            "font-size: 11pt; font-weight: bold; padding-left: 6px;"
            f"border-left: 4px solid {color};"
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
            pending = QLabel("Procesamiento aún no implementado (llega en la Fase 3).")
            pending.setWordWrap(True)
            pending.setStyleSheet("color: #D9A441;")
            layout.addWidget(pending)

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
        for spec in definition.outputs:
            form.addRow(self._socket_label(spec.display_label, spec.type), QLabel("salida"))
        layout.addWidget(sockets)
        layout.addStretch(1)

    @staticmethod
    def _socket_label(label: str, socket_type) -> QLabel:
        widget = QLabel(
            f"<span style='color:{socket_type.color}'>●</span> {label} "
            f"<span style='color:{Colors.TEXT_DIM}'>({socket_type.value})</span>"
        )
        widget.setTextFormat(Qt.TextFormat.RichText)
        return widget

    def _refresh_connected(self) -> None:
        if self.node_id is None:
            return
        connected = self.graph.connected_inputs(self.node_id)
        for name, widget in self._input_widgets.items():
            is_connected = name in connected
            widget.setEnabled(not is_connected)
            widget.setToolTip("Conectada: el valor proviene de otro nodo" if is_connected else "")

    # -- eventos del grafo -------------------------------------------------------------

    def _on_graph_event(self, event: GraphEvent) -> None:
        if event.kind is GraphEventKind.CLEARED:
            self.show_selection([])
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
