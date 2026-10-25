"""Diálogo para activar las librerías adicionales de nodos del proyecto."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.libraries import LibraryInfo, available_libraries
from palantir_nodes.ui.theme import Colors


def library_html(library: LibraryInfo) -> str:
    """Descripción de una librería: qué hace, qué nodos añade y qué necesita instalar."""
    nodes = "".join(f"<li><b>{escape(cls.label)}</b></li>" for cls in library.nodes)
    parts = [
        f"<h3>{escape(library.label)}</h3>",
        f"<p>{escape(library.description)}</p>",
        f"<p>Nodos que añade:</p><ul>{nodes}</ul>",
    ]
    if library.requirements:
        rows = []
        for requirement in library.requirements:
            if requirement.installed:
                state = "<span style='color:#7CC77C'>instalado</span>"
            else:
                state = f"<span style='color:{Colors.LINK_INVALID}'>falta instalarlo</span>"
            rows.append(f"<li><code>{escape(requirement.package)}</code> — {state}</li>")
        parts.append(f"<p>Paquetes necesarios:</p><ul>{''.join(rows)}</ul>")
        if library.missing:
            parts.append(
                "<p>Para instalarlo, en la terminal de este proyecto:<br>"
                f"<code>{escape(library.install_command)}</code></p>"
                "<p>Puedes activar la librería igualmente; los nodos avisarán al ejecutarse "
                "si falta el paquete.</p>"
            )
        parts.append("<p>El script exportado importa y pide estos paquetes automáticamente.</p>")
    return "".join(parts)


class LibrariesDialog(QDialog):
    """Lista de librerías con casilla de activación. ``selected_ids()`` da las marcadas."""

    def __init__(
        self,
        enabled: list[str],
        parent: QWidget | None = None,
        *,
        usage: dict[str, int] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Librerías del proyecto")
        self.resize(760, 460)
        self._libraries = available_libraries()
        self._usage = usage or {}

        intro = QLabel(
            "Las librerías activas se guardan con el proyecto: sus nodos aparecen en el menú de "
            "añadir y el script exportado incluye lo que necesiten."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {Colors.TEXT_DIM};")

        self.listing = QListWidget()
        self.listing.setMaximumWidth(260)
        for library in self._libraries:
            item = QListWidgetItem(library.label)
            item.setData(Qt.ItemDataRole.UserRole, library.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if library.id in enabled else Qt.CheckState.Unchecked
            )
            self.listing.addItem(item)

        self.details = QTextBrowser()
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet(f"color: {Colors.LINK_INVALID};")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        body = QHBoxLayout()
        body.addWidget(self.listing)
        body.addWidget(self.details, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(body, 1)
        layout.addWidget(self.warning)
        layout.addWidget(buttons)

        self.listing.currentItemChanged.connect(self._show_current)
        self.listing.itemChanged.connect(lambda _item: self._update_warning())
        if self._libraries:
            self.listing.setCurrentRow(0)
        self._update_warning()

    def _library_of(self, item: QListWidgetItem | None) -> LibraryInfo | None:
        if item is None:
            return None
        library_id = item.data(Qt.ItemDataRole.UserRole)
        return next((lib for lib in self._libraries if lib.id == library_id), None)

    def _show_current(self, item: QListWidgetItem | None, _previous=None) -> None:
        library = self._library_of(item)
        self.details.setHtml(library_html(library) if library else "")

    def _update_warning(self) -> None:
        """Avisa de los nodos del grafo que se borrarían al desactivar una librería."""
        lost = []
        for row in range(self.listing.count()):
            item = self.listing.item(row)
            library = self._library_of(item)
            count = self._usage.get(library.id, 0) if library else 0
            if library and count and item.checkState() != Qt.CheckState.Checked:
                lost.append(f"{count} nodo(s) de «{library.label}»")
        self.warning.setText(
            "Al aceptar se eliminarán del grafo: " + ", ".join(lost) + "." if lost else ""
        )

    def selected_ids(self) -> list[str]:
        ids = []
        for row in range(self.listing.count()):
            item = self.listing.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids
