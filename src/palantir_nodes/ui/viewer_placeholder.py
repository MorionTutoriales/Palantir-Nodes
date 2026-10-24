"""Marcador del visor de resultados (se implementa en las Fases 3 y 5)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from palantir_nodes.ui.theme import Colors


class ViewerPlaceholder(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"background: {Colors.EDITOR_BG};")
        label = QLabel(
            "Visor de resultados\n\n"
            "No implementado todavía.\n"
            "Imágenes estáticas: Fase 3 · Video y cámara: Fase 5."
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        layout = QVBoxLayout(self)
        layout.addWidget(label)
