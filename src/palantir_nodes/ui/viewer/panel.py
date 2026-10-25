"""Visor de imágenes con zoom y desplazamiento."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.ui.theme import Colors

ZOOM_MIN = 0.02
ZOOM_MAX = 64.0


def ndarray_to_qimage(img: np.ndarray) -> QImage:
    """Convierte una imagen uint8 (gris, BGR o BGRA) en un QImage independiente."""
    if img.ndim == 3 and img.shape[2] == 1:
        img = img[:, :, 0]
    if img.ndim == 2:
        fmt = QImage.Format.Format_Grayscale8
    elif img.shape[2] == 3:
        fmt = QImage.Format.Format_BGR888
    else:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        fmt = QImage.Format.Format_RGBA8888
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    return QImage(img.data, w, h, img.strides[0], fmt).copy()


class ImageCanvas(QGraphicsView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self._item)
        self._fit = True
        self.setBackgroundBrush(QColor(Colors.EDITOR_BG))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    @property
    def zoom(self) -> float:
        return self.transform().m11()

    def set_image(self, img: np.ndarray) -> None:
        old = self._item.pixmap().size()
        self._item.setPixmap(QPixmap.fromImage(ndarray_to_qimage(img)))
        self.scene().setSceneRect(QRectF(self._item.boundingRect()))
        if self._fit or self._item.pixmap().size() != old:
            self.fit()

    def fit(self) -> None:
        self._fit = True
        if not self._item.pixmap().isNull():
            self.resetTransform()
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if not delta:
            return
        target = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * 1.2 ** (delta / 120)))
        factor = target / self.zoom
        if abs(factor - 1) > 1e-6:
            self._fit = False
            self.scale(factor, factor)
            self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, target < 3.0)

    def mouseDoubleClickEvent(self, event) -> None:
        self.fit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self.fit()


class ViewerPanel(QWidget):
    """Muestra la imagen del nodo elegido, o un mensaje si no hay nada que mostrar."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.canvas = ImageCanvas()
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setMargin(16)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message.setStyleSheet(f"background: {Colors.EDITOR_BG}; color: {Colors.TEXT_DIM};")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.message)
        self.stack.addWidget(self.canvas)

        self.source = QLabel()
        self.source.setStyleSheet(f"color: {Colors.TEXT_DIM}; padding: 3px 6px;")
        self.info = QLabel()
        self.info.setStyleSheet(f"color: {Colors.TEXT_DIM}; padding: 3px 6px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.source)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.info)
        self.show_message("Añade un Image Viewer o selecciona un nodo\ny pulsa Ejecutar.")

    def show_message(self, text: str, *, error: bool = False, source: str = "") -> None:
        self.message.setText(text)
        color = Colors.LINK_INVALID if error else Colors.TEXT_DIM
        self.message.setStyleSheet(f"background: {Colors.EDITOR_BG}; color: {color};")
        self.source.setText(source)
        self.info.setText("")
        self.stack.setCurrentWidget(self.message)

    def show_text(self, text: str, source: str = "") -> None:
        """Muestra un texto (seleccionable) en lugar de una imagen."""
        self.show_message(text if text else "(texto vacío)", source=source)

    def show_image(
        self,
        img: np.ndarray,
        source: str,
        node_ms: float | None,
        total_ms: float,
        fps: float | None = None,
    ) -> None:
        self.canvas.set_image(img)
        self.stack.setCurrentWidget(self.canvas)
        self.source.setText(source)
        h, w = img.shape[:2]
        channels = 1 if img.ndim == 2 else img.shape[2]
        parts = [f"{w}×{h}", f"{channels} canal" + ("es" if channels != 1 else "")]
        parts.append("nodo: caché" if node_ms == 0 else f"nodo: {node_ms:.1f} ms")
        parts.append(f"total: {total_ms:.1f} ms")
        if fps is not None:
            parts.append(f"{fps:.1f} FPS")
        self.info.setText(" · ".join(parts))
