"""Representación visual de un nodo, al estilo de Blender.

Orden de filas: salidas (socket a la derecha), parámetros y entradas (socket a la
izquierda). Los valores se muestran y se editan dentro del nodo: clic para escribir,
elegir o conmutar, y arrastre horizontal para ajustar números (el panel de propiedades
sigue disponible).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QStyle

from palantir_nodes.core.graph import NodeInstance
from palantir_nodes.core.types import SocketType
from palantir_nodes.nodes.categories import get_category
from palantir_nodes.nodes.specs import ParamKind, ParamSpec, resolve_slider
from palantir_nodes.ui.editor.field_values import NUMERIC_KINDS, scrub_value
from palantir_nodes.ui.editor.socket_item import SocketItem
from palantir_nodes.ui.theme import Colors
from palantir_nodes.ui.viewer.panel import ndarray_to_qimage


@dataclass
class _Row:
    kind: str  # "output" | "param" | "input"
    name: str
    label: str
    y: float
    spec: ParamSpec | None = None  # parámetro o valor editable de una entrada
    socketed: bool = False  # parámetro con socket de entrada (ver ``ParamSpec.socket_type``)


PREVIEW_WIDTH = 172.0  # espacio máximo de la miniatura dentro del nodo
PREVIEW_HEIGHT = 110.0
PREVIEW_GAP = 6.0
TEXT_MAX_HEIGHT = 120.0  # alto máximo del texto de un String Viewer dentro del nodo
PREVIEW_MAX_UPSCALE = 3.0  # las imágenes diminutas se amplían como mucho 3 veces
DRAG_THRESHOLD = 4.0  # píxeles antes de que un clic en un campo pase a ser un arrastre


class NodeItem(QGraphicsItem):
    WIDTH = 190.0
    HEADER = 24.0
    ROW = 22.0
    PAD = 6.0
    CORNER = 6.0

    def __init__(self, node: NodeInstance) -> None:
        super().__init__()
        self.node = node
        self.node_id = node.id
        self.definition = node.definition
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(1)
        self.status: str | None = None
        self.status_message = ""
        self.setToolTip(self._base_tooltip())

        self._header_color = QColor(get_category(self.definition.category).color)
        self._title_font = QFont()
        self._title_font.setPointSizeF(9.0)
        self._title_font.setBold(True)
        self._font = QFont()
        self._font.setPointSizeF(8.5)
        self._connected: set[str] = set()
        self._hover_row: _Row | None = None
        self._hover_pin = False
        self._preview_pixmap: QPixmap | None = None
        self._preview_size = (0.0, 0.0)
        self._preview_extra = 0.0
        self._text: str | None = None  # texto completo que muestra el nodo (String Viewer)
        self._text_shown = ""  # lo que cabe en el nodo, con «…» si se recortó
        self._text_extra = 0.0
        self._field_press: dict | None = None
        self.pinned = False  # el visor está fijado en este nodo
        self.status: str | None = None
        self.status_message = ""

        self.input_sockets: dict[str, SocketItem] = {}
        self.output_sockets: dict[str, SocketItem] = {}
        self._rows: list[_Row] = []
        self._build()

    def _build(self) -> None:
        y = self.HEADER + self.PAD
        for spec in self.definition.outputs:
            socket = SocketItem(self, spec.name, spec.type, is_output=True)
            socket.setPos(self.WIDTH, y + self.ROW / 2)
            self.output_sockets[spec.name] = socket
            self._rows.append(_Row("output", spec.name, spec.display_label, y))
            y += self.ROW
        for spec in self.definition.params:
            socketed = spec.socket_type is not None
            if socketed:  # además de editarse, el parámetro se puede alimentar desde otro nodo
                socket = SocketItem(self, spec.name, spec.socket_type, is_output=False)
                socket.setPos(0.0, y + self.ROW / 2)
                self.input_sockets[spec.name] = socket
            self._rows.append(_Row("param", spec.name, spec.display_label, y, spec, socketed))
            y += self.ROW
        for spec in self.definition.inputs:
            socket = SocketItem(self, spec.name, spec.type, is_output=False)
            socket.setPos(0.0, y + self.ROW / 2)
            self.input_sockets[spec.name] = socket
            self._rows.append(_Row("input", spec.name, spec.display_label, y, spec.value_spec()))
            y += self.ROW
        self._base_height = y + self.PAD
        self._height = self._base_height

    @property
    def pinnable(self) -> bool:
        """Nodos con imagen: producen una o (los de salida) la reciben, y el visor puede fijarse."""
        definition = self.definition
        if any(o.type is SocketType.IMAGE for o in definition.outputs):
            return True
        if definition.shows_text:
            return True
        return not definition.outputs and any(i.type is SocketType.IMAGE for i in definition.inputs)

    def pin_rect(self) -> QRectF:
        return QRectF(self.WIDTH - 42, 4, 16, 16)

    def set_pinned(self, pinned: bool) -> None:
        if pinned != self.pinned:
            self.pinned = pinned
            self.update()

    def _paint_pin(self, painter: QPainter) -> None:
        rect = self.pin_rect()
        hovered = self._hover_pin
        painter.save()
        painter.translate(rect.center())
        painter.rotate(35)
        if self.pinned:
            painter.setPen(QPen(QColor("#3A2E0A"), 1))
            painter.setBrush(QColor("#F2C14E"))
        else:
            painter.setPen(QPen(QColor("#FFFFFF" if hovered else "#E4B8C0"), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(-3.5, -7, 7, 5), 1.5, 1.5)  # cabeza
        painter.drawLine(QPointF(-5, -2), QPointF(5, -2))  # base
        painter.drawLine(QPointF(0, -2), QPointF(0, 7))  # aguja
        painter.restore()

    @property
    def height(self) -> float:
        return self._height

    # -- previsualización --------------------------------------------------------------

    @property
    def has_preview(self) -> bool:
        return self._preview_pixmap is not None

    def preview_rect(self) -> QRectF | None:
        """Rectángulo (coordenadas locales) que ocupa la miniatura, o ``None``."""
        if self._preview_pixmap is None:
            return None
        width, height = self._preview_size
        top = self._base_height - self.PAD + PREVIEW_GAP
        return QRectF((self.WIDTH - width) / 2, top, width, height)

    def set_preview(self, image: np.ndarray | None) -> None:
        """Muestra una miniatura al final del nodo (``None`` la quita y recupera la altura)."""
        if image is None:
            if self._preview_pixmap is None:
                return
            self._preview_pixmap = None
            self._preview_extra = 0.0
        else:
            img_h, img_w = image.shape[:2]
            scale = min(PREVIEW_WIDTH / img_w, PREVIEW_HEIGHT / img_h, PREVIEW_MAX_UPSCALE)
            self._preview_pixmap = QPixmap.fromImage(ndarray_to_qimage(image))
            self._preview_size = (img_w * scale, img_h * scale)
            self._preview_extra = self._preview_size[1] + PREVIEW_GAP
        self._apply_height()

    def _apply_height(self) -> None:
        new_height = self._base_height + self._preview_extra + self._text_extra
        if new_height != self._height:
            self.prepareGeometryChange()
            self._height = new_height
        self.update()

    # -- texto (String Viewer) -----------------------------------------------------------

    @property
    def text(self) -> str | None:
        return self._text

    def text_rect(self) -> QRectF | None:
        """Rectángulo (coordenadas locales) del texto mostrado, o ``None``."""
        if self._text is None:
            return None
        top = self._base_height - self.PAD + self._preview_extra + PREVIEW_GAP
        return QRectF(8, top, self.WIDTH - 16, self._text_extra - PREVIEW_GAP)

    def set_text(self, text: str | None) -> None:
        """Muestra un texto dentro del nodo (``None`` lo quita). Si no cabe se recorta con «…»."""
        if text == self._text:
            return
        self._text = text
        if text is None:
            self._text_shown, self._text_extra = "", 0.0
            self.setToolTip(self._base_tooltip())
        else:
            self._text_shown, height = self._fit_text(text)
            self._text_extra = height + PREVIEW_GAP
            self.setToolTip(text[:2000] + ("…" if len(text) > 2000 else ""))
        self._apply_height()

    def _fit_text(self, text: str) -> tuple[str, float]:
        """Parte del texto que cabe en ``TEXT_MAX_HEIGHT`` y el alto que ocupa."""
        metrics = QFontMetricsF(self._font)
        flags = int(Qt.TextFlag.TextWordWrap)
        box = QRectF(0, 0, self.WIDTH - 24, 100000)

        def height_of(value: str) -> float:
            return metrics.boundingRect(box, flags, value).height() + 8

        if not text:
            return "", metrics.height() + 8
        if height_of(text) <= TEXT_MAX_HEIGHT:
            return text, height_of(text)
        low, high = 0, len(text)
        while low < high:  # la mayor longitud que cabe junto con la «…»
            mid = (low + high + 1) // 2
            if height_of(text[:mid] + "…") <= TEXT_MAX_HEIGHT:
                low = mid
            else:
                high = mid - 1
        shown = text[:low] + "…"
        return shown, min(height_of(shown), TEXT_MAX_HEIGHT)

    def socket(self, name: str, is_output: bool) -> SocketItem | None:
        return (self.output_sockets if is_output else self.input_sockets).get(name)

    def set_connected_inputs(self, names: set[str]) -> None:
        if names != self._connected:
            self._connected = set(names)
            self.update()

    def refresh(self) -> None:
        self.update()

    def _base_tooltip(self) -> str:
        base = self.definition.description or self.definition.label
        if self.status:
            return f"{base}\n\n⚠ {self.status_message}"
        return base

    def set_status(self, kind: str | None, message: str = "") -> None:
        """``kind``: ``"error"`` (falló), ``"blocked"`` (depende de uno que falló) o ``None``."""
        if (kind, message) == (self.status, self.status_message):
            return
        self.status, self.status_message = kind, message
        self.setToolTip(self._base_tooltip())
        self.update()

    # -- geometría ---------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, self.WIDTH + 4, self._height + 4)

    def _body_path(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.WIDTH, self._height), self.CORNER, self.CORNER)
        return path

    def shape(self) -> QPainterPath:
        return self._body_path()

    # -- pintado -----------------------------------------------------------------------

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = self._body_path()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.fillPath(body, QColor(Colors.NODE_BODY))
        painter.save()
        painter.setClipPath(body)
        painter.fillRect(QRectF(0, 0, self.WIDTH, self.HEADER), self._header_color)
        painter.restore()

        if self.status == "error":
            pen = QPen(QColor(Colors.LINK_INVALID), 2.4)
        elif selected:
            pen = QPen(QColor(Colors.NODE_SELECTED), 1.8)
        else:
            pen = QPen(QColor(Colors.NODE_BORDER), 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body)
        if self.status == "blocked":
            painter.setPen(QPen(QColor("#B8862B"), 1.6, Qt.PenStyle.DashLine))
            painter.drawPath(body)
        if self.status:
            badge = QRectF(self.WIDTH - 20, 4, 16, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(Colors.LINK_INVALID if self.status == "error" else "#B8862B"))
            painter.drawEllipse(badge)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "!")

        if self.pinnable:
            self._paint_pin(painter)

        painter.setFont(self._title_font)
        painter.setPen(QColor(Colors.NODE_TEXT))
        metrics = QFontMetricsF(self._title_font)
        reserved = 48 if self.pinnable else 16
        title_rect = QRectF(8, 0, self.WIDTH - reserved, self.HEADER)
        title = metrics.elidedText(
            self.definition.label, Qt.TextElideMode.ElideRight, title_rect.width()
        )
        painter.drawText(
            title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title
        )

        painter.setFont(self._font)
        for row in self._rows:
            self._paint_row(painter, row)
        self._paint_preview(painter)
        self._paint_text(painter)

    def _paint_text(self, painter: QPainter) -> None:
        rect = self.text_rect()
        if rect is None:
            return
        painter.setPen(QPen(QColor("#151515"), 1))
        painter.setBrush(QColor(Colors.BASE))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(Colors.NODE_TEXT))
        painter.setFont(self._font)
        flags = Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap
        painter.drawText(rect.adjusted(6, 4, -6, -4), int(flags), self._text_shown)

    def _paint_preview(self, painter: QPainter) -> None:
        rect = self.preview_rect()
        if rect is None:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setPen(QPen(QColor("#151515"), 1))
        painter.setBrush(QColor(Colors.BASE))
        painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 3, 3)
        painter.drawPixmap(rect, self._preview_pixmap, QRectF(self._preview_pixmap.rect()))

    def _paint_row(self, painter: QPainter, row: _Row) -> None:
        text_color = QColor(Colors.NODE_TEXT)
        align_v = Qt.AlignmentFlag.AlignVCenter
        if row.kind == "output":
            rect = QRectF(10, row.y, self.WIDTH - 20, self.ROW)
            painter.setPen(text_color)
            painter.drawText(rect, align_v | Qt.AlignmentFlag.AlignRight, row.label)
            return
        driven = row.socketed and row.name in self._connected  # su valor viene de otro nodo
        if (row.kind == "input" and (row.spec is None or row.name in self._connected)) or driven:
            rect = QRectF(12, row.y, self.WIDTH - 22, self.ROW)
            painter.setPen(text_color)
            painter.drawText(rect, align_v | Qt.AlignmentFlag.AlignLeft, row.label)
            return

        values = self.node.params if row.kind == "param" else self.node.input_values
        self._paint_field(painter, row, values.get(row.name))

    def _field_rect(self, row: _Row) -> QRectF:
        left = 12.0 if row.kind == "input" or row.socketed else 8.0
        return QRectF(left, row.y + 2, self.WIDTH - left - 8, self.ROW - 4)

    def _paint_field(self, painter: QPainter, row: _Row, value: Any) -> None:
        spec = row.spec
        field = self._field_rect(row)
        hovered = row is self._hover_row
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Colors.NODE_FIELD_HOVER if hovered else Colors.NODE_FIELD))
        painter.drawRoundedRect(field, 4, 4)

        inner = field.adjusted(6, 0, -6, 0)
        painter.setPen(QColor(Colors.NODE_TEXT))
        align_v = Qt.AlignmentFlag.AlignVCenter
        metrics = QFontMetricsF(self._font)

        if spec.kind is ParamKind.BOOL:
            box = QRectF(inner.left(), inner.center().y() - 5, 10, 10)
            painter.setBrush(QColor(Colors.ACCENT) if value else QColor(Colors.BASE))
            painter.setPen(QPen(QColor("#151515"), 1))
            painter.drawRoundedRect(box, 2, 2)
            painter.setPen(QColor(Colors.NODE_TEXT))
            painter.drawText(
                inner.adjusted(16, 0, 0, 0), align_v | Qt.AlignmentFlag.AlignLeft, row.label
            )
            return

        if spec.kind is ParamKind.COLOR:
            painter.drawText(inner, align_v | Qt.AlignmentFlag.AlignLeft, row.label)
            swatch = QRectF(inner.right() - 46, inner.top() + 3, 46, inner.height() - 6)
            painter.setBrush(QColor(*value))
            painter.setPen(QPen(QColor("#151515"), 1))
            painter.drawRoundedRect(swatch, 3, 3)
            return

        if spec.range_params is not None and row.kind == "param":
            self._paint_slider(painter, row, field, inner)
            return

        text = spec.format(value)
        label_width = metrics.horizontalAdvance(row.label + "  ")
        value_text = metrics.elidedText(
            text, Qt.TextElideMode.ElideMiddle, max(20.0, inner.width() - label_width)
        )
        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.drawText(inner, align_v | Qt.AlignmentFlag.AlignLeft, row.label)
        painter.setPen(QColor(Colors.NODE_TEXT))
        painter.drawText(inner, align_v | Qt.AlignmentFlag.AlignRight, value_text)

    def _slider_state(self, row: _Row) -> tuple[float, float, float, bool]:
        """``(mínimo, máximo, valor, solo_enteros)`` efectivos del deslizador de la fila."""
        lo_name, hi_name, int_name = row.spec.range_params
        params = self.node.params
        integer = bool(params.get(int_name))
        low, high, value = resolve_slider(
            params.get(lo_name, 0.0), params.get(hi_name, 1.0), params.get(row.name, 0.0), integer
        )
        return low, high, value, integer

    def _paint_slider(self, painter: QPainter, row: _Row, field: QRectF, inner: QRectF) -> None:
        low, high, value, integer = self._slider_state(row)
        fraction = (value - low) / (high - low) if high > low else 0.0
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(field, 4, 4)
        painter.setClipPath(clip)
        fill = QRectF(field.left(), field.top(), field.width() * fraction, field.height())
        painter.fillRect(fill, QColor(Colors.ACCENT))
        painter.restore()
        text = f"{value:.0f}" if integer else f"{value:.{row.spec.decimals}f}"
        painter.setPen(QColor(Colors.NODE_TEXT))
        align_v = Qt.AlignmentFlag.AlignVCenter
        painter.drawText(inner, align_v | Qt.AlignmentFlag.AlignLeft, row.label)
        painter.drawText(inner, align_v | Qt.AlignmentFlag.AlignRight, text)

    def _slider_value_at(self, row: _Row, x: float) -> float:
        """Valor del deslizador para una posición horizontal local (se recorta al rango)."""
        low, high, _, integer = self._slider_state(row)
        field = self._field_rect(row)
        fraction = min(max((x - field.left()) / field.width(), 0.0), 1.0)
        value = low + (high - low) * fraction
        return resolve_slider(low, high, value, integer)[2]

    # -- edición de valores dentro del nodo --------------------------------------------

    def _is_editable(self, row: _Row) -> bool:
        if row.spec is None:
            return False
        return row.name not in self._connected  # un valor conectado no se edita en el nodo

    def field_at(self, pos: QPointF) -> _Row | None:
        """Campo editable (parámetro o entrada sin conectar) bajo ``pos`` (coords. locales)."""
        for row in self._rows:
            if self._is_editable(row) and self._field_rect(row).contains(pos):
                return row
        return None

    def field_scene_rect(self, name: str, target: str = "param") -> QRectF | None:
        """Rectángulo en la escena de un campo (``target``: ``"param"`` o ``"input"``)."""
        for row in self._rows:
            if row.kind == target and row.name == name and self._is_editable(row):
                return self.mapRectToScene(self._field_rect(row))
        return None

    def _current_value(self, row: _Row) -> Any:
        values = self.node.params if row.kind == "param" else self.node.input_values
        return values.get(row.name)

    def _apply_value(self, row: _Row, value: Any) -> None:
        controller = self.scene().controller
        if row.kind == "param":
            controller.set_param(self.node_id, row.name, value)
        else:
            controller.set_input_value(self.node_id, row.name, value)

    def _set_hover_row(self, row: _Row | None) -> None:
        if row is not self._hover_row:
            self._hover_row = row
            self.update()

    def _set_hover_pin(self, hovered: bool) -> None:
        if hovered != self._hover_pin:
            self._hover_pin = hovered
            self.update()

    def hoverMoveEvent(self, event) -> None:
        over_pin = self.pinnable and self.pin_rect().contains(event.pos())
        self._set_hover_pin(over_pin)
        if over_pin:
            self._set_hover_row(None)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Fijar el visor en este nodo" if not self.pinned else "Soltar el visor")
            return
        self.setToolTip(self._base_tooltip())
        row = self.field_at(event.pos())
        self._set_hover_row(row)
        if row is None:
            self.unsetCursor()
        elif row.spec.kind in NUMERIC_KINDS or row.spec.range_params:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._set_hover_pin(False)
        self._set_hover_row(None)
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.pinnable
            and self.pin_rect().contains(event.pos())
        ):
            self.scene().pin_requested.emit(self.node_id)
            event.accept()
            return
        row = self.field_at(event.pos()) if event.button() == Qt.MouseButton.LeftButton else None
        if row is None:
            super().mousePressEvent(event)
            return
        scene = self.scene()
        if not self.isSelected() or len(scene.selectedItems()) > 1:
            scene.clearSelection()  # el nodo editado pasa a ser la única selección
            self.setSelected(True)
        self._field_press = {
            "row": row,
            "start": event.scenePos(),
            "value0": self._current_value(row),
            "scrubbing": False,
            "moved": False,
            "slider": row.spec.range_params is not None and row.kind == "param",
        }
        if self._field_press["slider"]:  # el deslizador salta a donde se pulsa
            self._field_press["scrubbing"] = True
            self._apply_value(row, self._slider_value_at(row, event.pos().x()))
        event.accept()  # el campo no arrastra el nodo

    def mouseMoveEvent(self, event) -> None:
        press = self._field_press
        if press is None:
            super().mouseMoveEvent(event)
            return
        row = press["row"]
        if press["slider"]:
            self._apply_value(row, self._slider_value_at(row, event.pos().x()))
            event.accept()
            return
        offset = event.scenePos() - press["start"]
        dx = offset.x()
        if offset.manhattanLength() >= DRAG_THRESHOLD:
            press["moved"] = True  # un arrastre sin efecto no cuenta como clic
        if not press["scrubbing"]:
            if abs(dx) < DRAG_THRESHOLD or row.spec.kind not in NUMERIC_KINDS:
                return
            press["scrubbing"] = True
        fine = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._apply_value(row, scrub_value(row.spec, press["value0"], dx, fine=fine))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        press, self._field_press = self._field_press, None
        if press is None:
            super().mouseReleaseEvent(event)
            return
        event.accept()
        if press["scrubbing"] or press["moved"]:
            return
        row = press["row"]
        if row.spec.kind is ParamKind.BOOL:
            self._apply_value(row, not self._current_value(row))
        else:
            rect = self.mapRectToScene(self._field_rect(row))
            self.scene().field_edit_requested.emit(self.node_id, row.kind, row.name, rect)

    def mouseDoubleClickEvent(self, event) -> None:
        row = self.field_at(event.pos()) if event.button() == Qt.MouseButton.LeftButton else None
        if row is not None and row.spec.range_params is not None and row.kind == "param":
            rect = self.mapRectToScene(self._field_rect(row))
            self.scene().field_edit_requested.emit(self.node_id, row.kind, row.name, rect)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # -- eventos -----------------------------------------------------------------------

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            if scene is not None and hasattr(scene, "node_item_moved"):
                scene.node_item_moved(self.node_id)
        return super().itemChange(change, value)

    def scene_position(self) -> tuple[float, float]:
        pos: QPointF = self.pos()
        return (pos.x(), pos.y())


def socket_offset(definition, name: str, *, is_output: bool) -> tuple[float, float]:
    """Posición local (x, y) de un socket de un tipo de nodo, sin crear el elemento visual.

    Replica la disposición de ``NodeItem._build`` (salidas, parámetros y luego entradas);
    una prueba comprueba que ambas coinciden.
    """
    y = NodeItem.HEADER + NodeItem.PAD
    for spec in definition.outputs:
        if is_output and spec.name == name:
            return (NodeItem.WIDTH, y + NodeItem.ROW / 2)
        y += NodeItem.ROW
    for param in definition.params:
        if not is_output and param.name == name and param.socket_type is not None:
            return (0.0, y + NodeItem.ROW / 2)
        y += NodeItem.ROW
    for spec in definition.inputs:
        if not is_output and spec.name == name:
            return (0.0, y + NodeItem.ROW / 2)
        y += NodeItem.ROW
    raise KeyError(f"'{definition.label}' no tiene el socket '{name}'")
