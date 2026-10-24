"""Conexiones Bézier entre sockets."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyle

from palantir_nodes.core.graph import Link
from palantir_nodes.ui.editor.socket_item import SocketItem
from palantir_nodes.ui.theme import Colors


def bezier_path(start: QPointF, end: QPointF) -> QPainterPath:
    """Curva horizontal tipo Blender desde una salida (``start``) hacia una entrada."""
    dx = max(abs(end.x() - start.x()) * 0.5, 40.0)
    path = QPainterPath(start)
    path.cubicTo(start + QPointF(dx, 0), end - QPointF(dx, 0), end)
    return path


class _PathItem(QGraphicsPathItem):
    """Path con área de selección más ancha que el trazo visible."""

    PICK_WIDTH = 10.0

    def __init__(self) -> None:
        super().__init__()
        self._shape = QPainterPath()
        self._bounds = QRectF()

    def set_bezier(self, start: QPointF, end: QPointF) -> None:
        path = bezier_path(start, end)
        self.prepareGeometryChange()
        stroker = QPainterPathStroker()
        stroker.setWidth(self.PICK_WIDTH)
        self._shape = stroker.createStroke(path)
        self._bounds = self._shape.boundingRect()
        self.setPath(path)

    def shape(self) -> QPainterPath:
        return self._shape

    def boundingRect(self) -> QRectF:
        return self._bounds


class LinkItem(_PathItem):
    def __init__(self, link: Link, src: SocketItem, dst: SocketItem) -> None:
        super().__init__()
        self.link = link
        self.link_id = link.id
        self.src = src
        self.dst = dst
        self._hover = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setZValue(0)
        self.update_path()

    def update_path(self) -> None:
        self.set_bezier(self.src.center(), self.dst.center())

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = self.path()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        outline = QColor(Colors.LINK_SELECTED) if selected else QColor("#111111")
        painter.setPen(
            QPen(outline, 5.0 if selected else 3.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPath(path)

        gradient = QLinearGradient(path.pointAtPercent(0), path.pointAtPercent(1))
        src_color = QColor(self.src.socket_type.color)
        dst_color = QColor(self.dst.socket_type.color)
        if self._hover:
            src_color, dst_color = src_color.lighter(130), dst_color.lighter(130)
        gradient.setColorAt(0, src_color)
        gradient.setColorAt(1, dst_color)
        pen = QPen(gradient, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()


class DragLinkItem(_PathItem):
    """Conexión temporal mientras el usuario arrastra desde un socket."""

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(10)
        self._color = QColor(Colors.LINK_NEUTRAL)
        self._dashed = True

    def set_state(self, color: str, dashed: bool) -> None:
        self._color = QColor(color)
        self._dashed = dashed
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, 2.0)
        if self._dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self.path())
