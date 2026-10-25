"""Diálogo para elegir las carpetas de importación de los nodos personalizados."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.customnodes.paths import missing_paths, normalize
from palantir_nodes.ui.theme import Colors


class ImportPathsDialog(QDialog):
    """Lista editable de carpetas. ``paths()`` da el resultado."""

    def __init__(self, paths: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rutas de importación")
        self.resize(620, 360)
        intro = QLabel(
            "Carpetas donde los nodos personalizados buscan módulos de Python al hacer "
            "<code>import</code> (van al final de la ruta de búsqueda). Indica la carpeta que "
            "<b>contiene</b> el módulo o paquete: para <code>C:\\libs\\mi_lib\\__init__.py</code> "
            "añade <code>C:\\libs</code>.<br><br>Las librerías instaladas con pip en el Python de "
            f"la aplicación no necesitan nada:<br><code>{sys.executable}</code>"
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {Colors.TEXT_DIM};")

        self.listing = QListWidget()
        self.btn_add = QPushButton("Añadir carpeta…")
        self.btn_remove = QPushButton("Quitar")
        self.btn_remove.setEnabled(False)
        self.btn_add.clicked.connect(self.add_folder)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.listing.itemSelectionChanged.connect(
            lambda: self.btn_remove.setEnabled(bool(self.listing.selectedItems()))
        )
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {Colors.LINK_INVALID};")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_remove)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.listing, 1)
        layout.addLayout(row)
        layout.addWidget(self.note)
        layout.addWidget(buttons)
        for path in paths:
            self._append(path)
        self._refresh_note()

    # -- edición ---------------------------------------------------------------------------

    def _append(self, path: str) -> bool:
        folder = normalize(path)
        if not folder or folder in self.paths():
            return False
        item = QListWidgetItem(folder)
        self.listing.addItem(item)
        return True

    def add_path(self, path: str) -> bool:
        """Añade una carpeta (``False`` si ya estaba o está vacía)."""
        added = self._append(path)
        self._refresh_note()
        return added

    def add_folder(self) -> None:
        start = self.paths()[-1] if self.paths() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Carpeta con módulos de Python", start)
        if folder:
            self.add_path(folder)

    def remove_selected(self) -> None:
        for item in self.listing.selectedItems():
            self.listing.takeItem(self.listing.row(item))
        self._refresh_note()

    def _refresh_note(self) -> None:
        missing = set(missing_paths(self.paths()))
        for row in range(self.listing.count()):
            item = self.listing.item(row)
            gone = item.text() in missing
            item.setForeground(QColor(Colors.LINK_INVALID if gone else Colors.NODE_TEXT))
            item.setToolTip("Esta carpeta no existe" if gone else "")
        self.note.setText(
            f"No existe: {', '.join(sorted(missing))}. Se guarda igualmente." if missing else ""
        )

    def paths(self) -> list[str]:
        return [self.listing.item(row).text() for row in range(self.listing.count())]
