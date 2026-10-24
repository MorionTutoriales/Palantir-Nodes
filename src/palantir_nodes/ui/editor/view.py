"""Vista del editor: cuadrícula, zoom, desplazamiento, menús y atajos."""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QLineF, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QColorDialog, QGraphicsView, QInputDialog, QMenu

from palantir_nodes.nodes.categories import get_category
from palantir_nodes.nodes.registry import NodeRegistry
from palantir_nodes.ui.editor.controller import EditorController
from palantir_nodes.ui.editor.field_editing import FieldEditor
from palantir_nodes.ui.editor.frame_item import FrameItem
from palantir_nodes.ui.editor.link_item import LinkItem
from palantir_nodes.ui.editor.node_item import NodeItem
from palantir_nodes.ui.editor.scene import NodeScene
from palantir_nodes.ui.editor.search_popup import NodeSearchPopup
from palantir_nodes.ui.editor.socket_item import SocketItem
from palantir_nodes.ui.theme import Colors

GRID_STEP = 20
GRID_MAJOR_EVERY = 5
ZOOM_MIN = 0.1
ZOOM_MAX = 3.0
ZOOM_STEP = 1.15


class NodeView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(
        self, scene: NodeScene, controller: EditorController, registry: NodeRegistry, parent=None
    ) -> None:
        super().__init__(scene, parent)
        self.node_scene = scene
        self.controller = controller
        self.registry = registry
        self._panning = False
        self._pan_last = QPointF()
        self.grid_visible = True
        self.zoom_step = ZOOM_STEP

        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.centerOn(0, 0)
        self._create_actions()
        self.field_editor = FieldEditor(self)

    # -- acciones y atajos -------------------------------------------------------------

    def _action(self, text: str, shortcuts: list[str], slot) -> QAction:
        action = QAction(text, self)
        action.setShortcuts([QKeySequence(s) for s in shortcuts])
        # Solo cuando el editor tiene el foco, para no interferir con los campos de texto.
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _create_actions(self) -> None:
        self.action_add = self._action("Añadir nodo…", ["Shift+A"], self._add_menu_at_cursor)
        self.action_search = self._action("Buscar nodo…", ["Ctrl+F"], self._search_at_cursor)
        self.action_delete = self._action(
            "Eliminar", ["X", "Delete"], self.controller.delete_selection
        )
        self.action_duplicate = self._action(
            "Duplicar", ["Shift+D"], self.controller.duplicate_selection
        )
        self.action_copy = self._action("Copiar", ["Ctrl+C"], self.controller.copy_selection)
        self.action_paste = self._action(
            "Pegar", ["Ctrl+V"], lambda: self.controller.paste(self.cursor_scene_pos())
        )
        self.action_select_all = self._action("Seleccionar todo", ["A", "Ctrl+A"], self.select_all)
        self.action_deselect = self._action("Deseleccionar", ["Alt+A"], self.scene().clearSelection)
        self.action_frame = self._action("Encuadrar todo", ["Home"], self.frame_all)
        self.action_frame_nodes = self._action(
            "Enmarcar selección (frame)", ["Ctrl+J"], self.controller.frame_selection
        )
        self.action_add_frame = self._action("Añadir frame vacío", [], self._add_empty_frame)
        self.node_scene.frame_rename_requested.connect(self.rename_frame)

    def editor_actions(self) -> list[QAction | None]:
        """Acciones del editor para el menú Editar (``None`` = separador)."""
        return [
            self.action_add,
            self.action_search,
            None,
            self.action_frame_nodes,
            self.action_add_frame,
            None,
            self.action_copy,
            self.action_paste,
            self.action_duplicate,
            self.action_delete,
            None,
            self.action_select_all,
            self.action_deselect,
        ]

    def select_all(self) -> None:
        for item in self.node_scene.node_items.values():
            item.setSelected(True)

    # -- geometría ---------------------------------------------------------------------

    @property
    def zoom(self) -> float:
        return self.transform().m11()

    def cursor_scene_pos(self) -> QPointF | None:
        local = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(local):
            return self.mapToScene(local)
        return None

    def _cursor_or_center(self) -> tuple[QPoint, QPointF]:
        local = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(local):
            local = self.viewport().rect().center()
        return self.viewport().mapToGlobal(local), self.mapToScene(local)

    def set_grid_visible(self, visible: bool) -> None:
        if visible != self.grid_visible:
            self.grid_visible = visible
            self.viewport().update()

    def state(self) -> dict:
        """Zoom y punto central actuales (para guardarlos en el proyecto)."""
        center = self.mapToScene(self.viewport().rect().center())
        return {"zoom": self.zoom, "center": (center.x(), center.y())}

    def restore_state(self, zoom: float, center: tuple[float, float]) -> None:
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        self.centerOn(center[0], center[1])
        self.zoom_changed.emit(self.zoom)

    def frame_all(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            self.resetTransform()
            self.centerOn(0, 0)
        else:
            self.fitInView(rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)
            if self.zoom > 1.0:
                self.resetTransform()
                self.centerOn(rect.center())
        self.zoom_changed.emit(self.zoom)

    # -- fondo -------------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(Colors.EDITOR_BG))
        if not self.grid_visible:
            return
        zoom = self.zoom
        major_step = GRID_STEP * GRID_MAJOR_EVERY
        steps = [(major_step, Colors.GRID_MAJOR)]
        if zoom >= 0.45:
            steps.insert(0, (GRID_STEP, Colors.GRID_MINOR))
        for step, color in steps:
            left = math.floor(rect.left() / step) * step
            top = math.floor(rect.top() / step) * step
            lines = []
            x = left
            while x < rect.right():
                if step == major_step or x % major_step:
                    lines.append(QLineF(x, rect.top(), x, rect.bottom()))
                x += step
            y = top
            while y < rect.bottom():
                if step == major_step or y % major_step:
                    lines.append(QLineF(rect.left(), y, rect.right(), y))
                y += step
            pen = QPen(QColor(color), 1.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLines(lines)

    # -- zoom y desplazamiento ---------------------------------------------------------

    def wheelEvent(self, event) -> None:
        self.field_editor.close_inline(commit=True)  # el editor en línea no sigue al zoom
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = self.zoom_step ** (delta / 120)
        target = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))
        factor = target / self.zoom
        if abs(factor - 1.0) > 1e-6:
            self.scale(factor, factor)
            self.zoom_changed.emit(self.zoom)

    @staticmethod
    def _shift_as_ctrl(event: QMouseEvent) -> QMouseEvent:
        """Blender usa Shift para añadir a la selección; Qt usa Ctrl."""
        mods = event.modifiers()
        if not mods & Qt.KeyboardModifier.ShiftModifier:
            return event
        mods = (mods & ~Qt.KeyboardModifier.ShiftModifier) | Qt.KeyboardModifier.ControlModifier
        return QMouseEvent(
            event.type(),
            event.position(),
            event.globalPosition(),
            event.button(),
            event.buttons(),
            mods,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.field_editor.close_inline(commit=True)
            self._panning = True
            self._pan_last = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(self._shift_as_ctrl(event))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            h, v = self.horizontalScrollBar(), self.verticalScrollBar()
            h.setValue(h.value() - round(delta.x()))
            v.setValue(v.value() - round(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(self._shift_as_ctrl(event))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(self._shift_as_ctrl(event))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.node_scene.is_dragging_link:
            self.node_scene.cancel_link_drag()
            return
        super().keyPressEvent(event)

    def event(self, event: QEvent) -> bool:
        # Evita que Tab mueva el foco fuera del editor.
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Tab:
            return True
        return super().event(event)

    # -- menús -------------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        if self.node_scene.is_dragging_link:
            return
        scene_pos = self.mapToScene(event.pos())
        item = self.itemAt(event.pos())
        if isinstance(item, SocketItem):
            item = item.node_item
        if isinstance(item, NodeItem):
            if not item.isSelected():
                self.scene().clearSelection()
                item.setSelected(True)
            menu = QMenu(self)
            menu.addAction(self.action_copy)
            menu.addAction(self.action_duplicate)
            menu.addSeparator()
            menu.addAction(self.action_frame_nodes)
            menu.addSeparator()
            menu.addAction(self.action_delete)
            menu.exec(event.globalPos())
        elif isinstance(item, FrameItem):
            if not item.isSelected():
                self.scene().clearSelection()
                item.setSelected(True)
            menu = QMenu(self)
            rename = menu.addAction("Renombrar…")
            recolor = menu.addAction("Cambiar color…")
            menu.addSeparator()
            remove = menu.addAction("Eliminar frame (los nodos se conservan)")
            chosen = menu.exec(event.globalPos())
            if chosen is rename:
                self.rename_frame(item.frame_id)
            elif chosen is recolor:
                self.recolor_frame(item.frame_id)
            elif chosen is remove:
                self.controller.remove_items([], [], [item.frame_id])
        elif isinstance(item, LinkItem):
            menu = QMenu(self)
            remove = menu.addAction("Eliminar conexión")
            if menu.exec(event.globalPos()) is remove:
                self.controller.remove_items([], [item.link_id])
        else:
            self.show_add_menu(event.globalPos(), scene_pos)

    def show_add_menu(self, global_pos: QPoint, scene_pos: QPointF) -> None:
        menu = QMenu(self)
        search = menu.addAction("Buscar…")
        search.setShortcut(QKeySequence("Ctrl+F"))
        new_frame = menu.addAction("Añadir frame aquí")
        menu.addSeparator()
        for category, members in self.registry.by_category().items():
            sub = menu.addMenu(category)
            sub.setIcon(_color_icon(get_category(category).color))
            for cls in members:
                action = sub.addAction(cls.label)
                action.setToolTip(cls.description)
                action.setData(cls.type_id)
            sub.setToolTipsVisible(True)
        chosen = menu.exec(global_pos)
        if chosen is search:
            self.show_search(global_pos, scene_pos)
        elif chosen is new_frame:
            self.controller.add_frame(scene_pos.x(), scene_pos.y())
        elif chosen is not None and chosen.data():
            self.controller.add_node(chosen.data(), scene_pos)

    def _add_empty_frame(self) -> None:
        _, scene_pos = self._cursor_or_center()
        self.controller.add_frame(scene_pos.x(), scene_pos.y())

    def rename_frame(self, frame_id: str) -> None:
        frame = self.node_scene.graph.frames.get(frame_id)
        if frame is None:
            return
        text, ok = QInputDialog.getText(self, "Renombrar frame", "Título:", text=frame.title)
        if ok and text.strip():
            self.controller.edit_frame(frame_id, title=text)

    def recolor_frame(self, frame_id: str) -> None:
        frame = self.node_scene.graph.frames.get(frame_id)
        if frame is None:
            return
        color = QColorDialog.getColor(QColor(frame.color), self, "Color del frame")
        if color.isValid():
            self.controller.edit_frame(frame_id, color=color.name())

    def show_search(self, global_pos: QPoint, scene_pos: QPointF) -> None:
        popup = NodeSearchPopup(self.registry, self)
        popup.node_chosen.connect(lambda type_id: self.controller.add_node(type_id, scene_pos))
        popup.popup_at(global_pos)

    def _add_menu_at_cursor(self) -> None:
        self.show_add_menu(*self._cursor_or_center())

    def _search_at_cursor(self) -> None:
        self.show_search(*self._cursor_or_center())


def _color_icon(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)
