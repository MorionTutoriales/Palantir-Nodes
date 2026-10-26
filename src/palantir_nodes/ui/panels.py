"""Piezas comunes de los paneles: barra de título de los docks y estados vacíos."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.ui import icons
from palantir_nodes.ui.theme import Colors


class DockTitle(QWidget):
    """Barra de título de un panel: icono, título y botones de flotar y cerrar."""

    def __init__(self, title: str, icon_name: str, dock: QDockWidget) -> None:
        super().__init__(dock)
        self.setObjectName("DockTitle")
        self.dock = dock
        self.icon_name = icon_name
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        self.title_label = QLabel(title)
        self.btn_float = self._button("Separar o acoplar el panel")
        self.btn_close = self._button("Cerrar el panel (se vuelve a abrir en el menú Ver)")
        self.btn_float.clicked.connect(lambda: dock.setFloating(not dock.isFloating()))
        self.btn_close.clicked.connect(dock.close)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 6, 5)
        layout.setSpacing(6)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.btn_float)
        layout.addWidget(self.btn_close)
        self.refresh_icons()

    @staticmethod
    def _button(tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setIconSize(QSize(14, 14))
        button.setFixedSize(22, 22)
        return button

    def refresh_icons(self) -> None:
        """Vuelve a dibujar los iconos con los colores del skin activo."""
        self.icon_label.setPixmap(icons.pixmap(self.icon_name, Colors.TEXT_DIM, 16))
        self.btn_float.setIcon(icons.icon("external-link", Colors.TEXT_DIM))
        self.btn_close.setIcon(icons.icon("x", Colors.TEXT_DIM))


class EmptyState(QWidget):
    """Icono grande y un texto centrados, para paneles sin contenido."""

    def __init__(self, icon_name: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addStretch(1)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch(1)
        self.refresh()

    def refresh(self, color: str | None = None) -> None:
        tint = color or Colors.TEXT_DIM
        self.icon_label.setPixmap(icons.pixmap(self.icon_name, tint, 48))
        self.text_label.setStyleSheet(f"color: {tint};")

    def set_state(self, icon_name: str, text: str, color: str | None = None) -> None:
        self.icon_name = icon_name
        self.text_label.setText(text)
        self.refresh(color)
