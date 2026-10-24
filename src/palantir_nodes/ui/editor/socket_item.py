"""Socket circular de entrada o salida, coloreado según su tipo."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from palantir_nodes.core.types import SocketType

if TYPE_CHECKING:
    from palantir_nodes.ui.editor.node_item import NodeItem


class SocketItem(QGraphicsItem):
    RADIUS = 5.0
    PICK_RADIUS = 10.0

    def __init__(
        self, node_item: NodeItem, name: str, socket_type: SocketType, is_output: bool
    ) -> None:
        super().__init__(node_item)
        self.node_item = node_item
        self.name = name
        self.socket_type = socket_type
        self.is_output = is_output
        self._color = QColor(socket_type.color)
        self._hover = False
        self._highlight: QColor | None = None
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        self.setToolTip(socket_type.value)

    @property
    def node_id(self) -> str:
        return self.node_item.node_id

    def center(self) -> QPointF:
        return self.scenePos()

    def boundingRect(self) -> QRectF:
        r = self.PICK_RADIUS
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), self.PICK_RADIUS, self.PICK_RADIUS)
        return path

    def set_highlight(self, color: QColor | None) -> None:
        if color != self._highlight:
            self._highlight = color
            self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = self.RADIUS * (1.3 if self._hover or self._highlight else 1.0)
        if self._highlight is not None:
            painter.setPen(QPen(self._highlight, 2.0))
        else:
            painter.setPen(QPen(QColor("#101010"), 1.2))
        painter.setBrush(self._color)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()
