"""Frame: rectángulo con título que agrupa nodos visualmente (al estilo de Blender).

El frame se agarra por su barra de título; la esquina inferior derecha lo redimensiona.
Al moverlo, lo acompañan los nodos (y frames) que estén completamente dentro de él. El
cuerpo del frame no captura el ratón, así que se puede seleccionar y arrastrar lo que
haya dentro sin tocar el frame.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent, QStyle

from palantir_nodes.core.graph import FRAME_MIN_HEIGHT, FRAME_MIN_WIDTH, Frame
from palantir_nodes.ui.editor.controller import FRAME_TITLE_HEIGHT
from palantir_nodes.ui.theme import Colors

HANDLE_SIZE = 18.0
CONTAIN_TOLERANCE = 3.0  # los nodos tienen un margen de 2 px en su rectángulo


class FrameItem(QGraphicsItem):
    def __init__(self, frame: Frame) -> None:
        super().__init__()
        self.frame_id = frame.id
        self.title = frame.title
        self.color = QColor(frame.color)
        self._width = frame.width
        self._height = frame.height
        self._drag: dict | None = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setZValue(-10)  # detrás de conexiones (0) y nodos (1)
        self._font = QFont()
        self._font.setPointSizeF(9.0)
        self._font.setBold(True)
        self.sync(frame)

    # -- modelo ------------------------------------------------------------------------

    def sync(self, frame: Frame) -> None:
        self.prepareGeometryChange()
        self.title = frame.title
        self.color = QColor(frame.color)
        self._width, self._height = frame.width, frame.height
        self.setPos(frame.x, frame.y)
        self.setToolTip(f"{frame.title}\nDoble clic en el título para renombrar")
        self.update()

    def scene_rect(self) -> QRectF:
        return QRectF(self.pos().x(), self.pos().y(), self._width, self._height)

    # -- geometría ---------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        return QRectF(-3, -3, self._width + 6, self._height + 6)

    def _title_rect(self) -> QRectF:
        return QRectF(0, 0, self._width, FRAME_TITLE_HEIGHT)

    def _handle_rect(self) -> QRectF:
        return QRectF(
            self._width - HANDLE_SIZE, self._height - HANDLE_SIZE, HANDLE_SIZE, HANDLE_SIZE
        )

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._title_rect())
        path.addRect(self._handle_rect())
        return path

    # -- pintado -----------------------------------------------------------------------

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = QRectF(0, 0, self._width, self._height)

        body = QColor(self.color)
        body.setAlpha(40)
        border = QColor(Colors.NODE_SELECTED) if selected else QColor(self.color)
        border.setAlpha(255 if selected else 130)
        painter.setPen(QPen(border, 2.0 if selected else 1.4))
        painter.setBrush(body)
        painter.drawRoundedRect(rect, 6, 6)

        bar = QPainterPath()
        bar.addRoundedRect(rect, 6, 6)
        painter.save()
        painter.setClipPath(bar)
        header = QColor(self.color)
        header.setAlpha(170)
        painter.fillRect(self._title_rect(), header)
        painter.restore()

        painter.setFont(self._font)
        painter.setPen(QColor("#F2F2F2"))
        title_rect = self._title_rect().adjusted(10, 0, -10, 0)
        elided = QFontMetricsF(self._font).elidedText(
            self.title, Qt.TextElideMode.ElideRight, title_rect.width()
        )
        painter.drawText(
            title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided
        )

        h = self._handle_rect()
        grip = QColor("#F2F2F2")
        grip.setAlpha(150)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grip)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(h.right() - 3, h.top() + 6),
                    QPointF(h.right() - 3, h.bottom() - 3),
                    QPointF(h.left() + 6, h.bottom() - 3),
                ]
            )
        )

    # -- ratón -------------------------------------------------------------------------

    def hoverMoveEvent(self, event) -> None:
        if self._handle_rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._title_rect().contains(event.pos()) and self.scene() is not None:
            self.scene().frame_rename_requested.emit(self.frame_id)
            event.accept()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(event)  # gestiona la selección
        if event.button() != Qt.MouseButton.LeftButton:
            return
        scene = self.scene()
        resizing = self._handle_rect().contains(event.pos())
        drag: dict = {
            "mode": "resize" if resizing else "move",
            "start": event.scenePos(),
            "pos0": self.pos(),
            "size0": (self._width, self._height),
            "nodes": {},
            "frames": {},
        }
        if not resizing:
            area = self.scene_rect().adjusted(
                -CONTAIN_TOLERANCE, -CONTAIN_TOLERANCE, CONTAIN_TOLERANCE, CONTAIN_TOLERANCE
            )
            for node_id, node in scene.node_items.items():
                if area.contains(node.sceneBoundingRect()):
                    drag["nodes"][node_id] = (node, node.pos())
            for frame_id, frame in scene.frame_items.items():
                if frame is not self and area.contains(frame.scene_rect()):
                    drag["frames"][frame_id] = (frame, frame.pos())
        self._drag = drag
        scene.suppress_node_moves = True  # el movimiento lo registra este frame, no la escena
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        drag = self._drag
        if drag is None:
            return
        delta = event.scenePos() - drag["start"]
        if drag["mode"] == "resize":
            w0, h0 = drag["size0"]
            self.prepareGeometryChange()
            self._width = max(FRAME_MIN_WIDTH, w0 + delta.x())
            self._height = max(FRAME_MIN_HEIGHT, h0 + delta.y())
            self.update()
            return
        self.setPos(drag["pos0"] + delta)
        for item, pos0 in (*drag["nodes"].values(), *drag["frames"].values()):
            item.setPos(pos0 + delta)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        drag, self._drag = self._drag, None
        if drag is None:
            return
        controller = self.scene().controller
        if drag["mode"] == "resize":
            controller.edit_frame(self.frame_id, width=self._width, height=self._height)
            return
        changes = {self.frame_id: {"x": self.pos().x(), "y": self.pos().y()}}
        for frame_id, (item, _) in drag["frames"].items():
            changes[frame_id] = {"x": item.pos().x(), "y": item.pos().y()}
        node_moves = {
            node_id: ((pos0.x(), pos0.y()), (item.pos().x(), item.pos().y()))
            for node_id, (item, pos0) in drag["nodes"].items()
        }
        controller.edit_frames(changes, node_moves)
        self.sync(self.scene().graph.frame(self.frame_id))  # por si el comando no cambió nada
