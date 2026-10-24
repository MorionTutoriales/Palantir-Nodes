"""Edición de los valores de un nodo directamente en el editor.

``FieldEditor`` atiende las peticiones de edición que emiten los nodos al hacer clic en un
campo: abre un editor de texto sobre el campo (números, vectores, texto), un menú
(enumerados) o un diálogo (color, archivos). Toda modificación pasa por el controlador,
así que se puede deshacer.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QKeyEvent
from PySide6.QtWidgets import QColorDialog, QFileDialog, QLineEdit, QMenu

from palantir_nodes.core.errors import PalantirError
from palantir_nodes.nodes.specs import ParamKind, ParamSpec
from palantir_nodes.ui.editor.field_values import (
    TEXT_KINDS,
    format_field_text,
    parse_field_text,
)

MIN_EDITOR_WIDTH = 90
MIN_EDITOR_HEIGHT = 22


class InlineEdit(QLineEdit):
    """Cuadro de texto de una sola vez: Enter o perder el foco confirma, Esc cancela."""

    finished = Signal(str, bool)  # (texto, confirmado)

    def __init__(self, parent, text: str) -> None:
        super().__init__(text, parent)
        self._done = False
        self.setStyleSheet(
            "QLineEdit { background: #262626; border: 1px solid #4772B3; border-radius: 4px;"
            " padding: 1px 6px; selection-background-color: #4772B3; }"
        )

    def _finish(self, commit: bool) -> None:
        if self._done:
            return
        self._done = True
        self.hide()
        self.finished.emit(self.text(), commit)
        self.deleteLater()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._finish(False)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish(True)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._finish(True)

    def cancel(self) -> None:
        self._finish(False)

    def commit(self) -> None:
        self._finish(True)


class FieldEditor(QObject):
    def __init__(self, view) -> None:
        super().__init__(view)
        self.view = view
        self.controller = view.controller
        self.graph = view.node_scene.graph
        self.inline: InlineEdit | None = None
        view.node_scene.field_edit_requested.connect(self.edit)

    # -- acceso al valor ---------------------------------------------------------------

    def _spec_and_value(self, node_id: str, target: str, name: str) -> tuple[ParamSpec, Any]:
        node = self.graph.node(node_id)
        if target == "param":
            return node.definition.param(name), node.params[name]
        return node.definition.input(name).value_spec(), node.input_values[name]

    def _set(self, node_id: str, target: str, name: str, value: Any) -> None:
        if target == "param":
            self.controller.set_param(node_id, name, value)
        else:
            self.controller.set_input_value(node_id, name, value)

    # -- punto de entrada --------------------------------------------------------------

    def edit(self, node_id: str, target: str, name: str, scene_rect: QRectF) -> None:
        self.close_inline(commit=True)
        try:
            spec, value = self._spec_and_value(node_id, target, name)
        except (PalantirError, KeyError, AttributeError):
            return  # el nodo o el campo ya no existen
        kind = spec.kind
        if kind is ParamKind.ENUM:
            choice = self._choose_enum(spec, value)
            if choice is not None:
                self._set(node_id, target, name, choice)
        elif kind is ParamKind.COLOR:
            color = self._choose_color(value)
            if color is not None:
                self._set(node_id, target, name, color)
        elif kind is ParamKind.FILE_PATH:
            path = self._choose_file(spec, value)
            if path:
                self._set(node_id, target, name, path)
        elif kind in TEXT_KINDS:
            self._open_inline(node_id, target, name, spec, value, scene_rect)

    # -- selectores (métodos separados para poder sustituirlos en las pruebas) ---------

    def _choose_enum(self, spec: ParamSpec, current: str) -> str | None:
        menu = QMenu(self.view)
        for value, label in spec.options:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value == current)
            action.setData(value)
        chosen = menu.exec(QCursor.pos())
        return chosen.data() if chosen is not None else None

    def _choose_color(self, current: tuple[int, int, int]) -> tuple[int, int, int] | None:
        color = QColorDialog.getColor(QColor(*current), self.view, "Seleccionar color")
        if not color.isValid():
            return None
        return (color.red(), color.green(), color.blue())

    def _choose_file(self, spec: ParamSpec, current: str) -> str | None:
        if spec.save_dialog:
            path, _ = QFileDialog.getSaveFileName(
                self.view, "Guardar como", current, spec.file_filter
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self.view, "Abrir archivo", current, spec.file_filter
            )
        return path or None

    # -- editor en línea ---------------------------------------------------------------

    def _open_inline(
        self,
        node_id: str,
        target: str,
        name: str,
        spec: ParamSpec,
        value: Any,
        scene_rect: QRectF,
    ) -> None:
        window = self.view.window()
        # Hijo de la ventana (no de la vista): así los atajos de una sola letra del editor
        # (X, A, Supr...) no se activan mientras se escribe.
        editor = InlineEdit(window, format_field_text(spec, value))
        viewport_rect = self.view.mapFromScene(scene_rect).boundingRect()
        top_left = self.view.viewport().mapTo(window, viewport_rect.topLeft())
        size = QSize(
            max(viewport_rect.width(), MIN_EDITOR_WIDTH),
            max(viewport_rect.height(), MIN_EDITOR_HEIGHT),
        )
        editor.setGeometry(QRect(QPoint(top_left), size))
        editor.setToolTip(spec.tooltip or "Enter confirma · Esc cancela")
        editor.finished.connect(
            lambda text, ok: self._finish_inline(node_id, target, name, spec, text, ok)
        )
        self.inline = editor
        editor.show()
        editor.raise_()
        editor.setFocus()
        editor.selectAll()

    def _finish_inline(
        self, node_id: str, target: str, name: str, spec: ParamSpec, text: str, commit: bool
    ) -> None:
        self.inline = None
        if not commit or node_id not in self.graph.nodes:
            return
        try:
            value = parse_field_text(spec, text)
        except ValueError as exc:
            self.controller.status_message.emit(f"{spec.display_label}: {exc}")
            return
        self._set(node_id, target, name, value)

    def close_inline(self, *, commit: bool) -> None:
        """Cierra el editor en línea abierto (p. ej. al hacer zoom o desplazar la vista)."""
        editor = self.inline
        if editor is None:
            return
        if commit:
            editor.commit()
        else:
            editor.cancel()
