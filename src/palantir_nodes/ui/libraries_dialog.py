"""Diálogo para activar las librerías adicionales de nodos del proyecto."""

from __future__ import annotations

import importlib
import sys
from html import escape

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.libraries import LibraryInfo, available_libraries
from palantir_nodes.ui.theme import Colors


def pip_command(packages: list[str], no_deps: bool = False) -> tuple[str, list[str]]:
    """Programa y argumentos que instalan ``packages`` en el mismo Python que ejecuta la app."""
    flags = ["--no-deps"] if no_deps else []
    return sys.executable, ["-m", "pip", "install", *flags, *packages]


def can_install() -> bool:
    """La instalación desde la app necesita un Python con pip (no una app empaquetada)."""
    return not getattr(sys, "frozen", False)


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
            rows.append(
                f"<li><code style='font-family:Consolas,monospace'>{escape(requirement.package)}</code> — {state}</li>"
            )
        parts.append(f"<p>Paquetes necesarios:</p><ul>{''.join(rows)}</ul>")
        if library.missing:
            parts.append(
                "<p>Pulsa «Instalar paquetes que faltan», o hazlo a mano en la terminal con "
                "el Python de esta aplicación:<br>"
                f"<code style='font-family:Consolas,monospace'>{escape(sys.executable)} -m {escape(library.install_command)}</code></p>"
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
        self.install_button = QPushButton("Instalar paquetes que faltan")
        self.install_button.setToolTip(
            "Instala con pip, en el mismo Python que ejecuta la aplicación, los paquetes que "
            "necesita la librería seleccionada"
        )
        self.install_button.clicked.connect(self.install_missing)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        self.log.setPlaceholderText("Aquí aparece el avance de la instalación")
        self.log.hide()
        self._process: QProcess | None = None
        self._installing: LibraryInfo | None = None
        self._steps: list[tuple[bool, list[str]]] = []
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet(f"color: {Colors.LINK_INVALID};")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        right = QVBoxLayout()
        right.addWidget(self.details, 1)
        right.addWidget(self.install_button)
        body = QHBoxLayout()
        body.addWidget(self.listing)
        body.addLayout(right, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(body, 1)
        layout.addWidget(self.log)
        layout.addWidget(self.warning)
        layout.addWidget(self.buttons)

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
        self._update_install_button()

    def _current_library(self) -> LibraryInfo | None:
        return self._library_of(self.listing.currentItem())

    def _update_install_button(self) -> None:
        library = self._current_library()
        missing = bool(library and library.missing)
        self.install_button.setVisible(missing)
        self.install_button.setEnabled(self._process is None and can_install())
        if missing and not can_install():
            self.install_button.setToolTip("Esta versión empaquetada no puede instalar paquetes")

    # -- instalación de paquetes -----------------------------------------------------------

    def install_missing(self) -> bool:
        """Instala con pip los paquetes que faltan de la librería seleccionada.

        Pide confirmación mostrando el comando. ``False`` si no hay nada que instalar, no se
        puede o el usuario cancela; el resultado llega de forma asíncrona (ver ``_finished``).
        """
        library = self._current_library()
        if library is None or not library.missing or self._process is not None:
            return False
        if not can_install():
            return False
        steps = library.install_steps()
        commands = "\n".join(
            f"{program} {' '.join(args)}"
            for program, args in (pip_command(packages, bare) for bare, packages in steps)
        )
        names = ", ".join(r.package for r in library.missing)
        answer = QMessageBox.question(
            self,
            "Instalar paquetes",
            f"Se descargarán e instalarán de PyPI: {names}.\n\nComandos:\n{commands}\n\n"
            "Puede tardar unos minutos y añadir otros paquetes de los que dependen. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.log.clear()
        self.log.show()
        self._installing, self._steps = library, list(steps)
        self.buttons.setEnabled(False)  # no se cierra el diálogo a mitad de una instalación
        self.listing.setEnabled(False)
        self._run_next_step()
        return True

    def _run_next_step(self) -> None:
        bare, packages = self._steps.pop(0)
        program, args = pip_command(packages, bare)
        self.log.appendPlainText(f"$ {program} {' '.join(args)}")
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._failed_to_start)
        self._process = process
        self._update_install_button()
        process.start(program, args)

    def _read_output(self) -> None:
        if self._process is not None:
            text = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
            self.log.appendPlainText(text.rstrip("\r\n"))

    def _failed_to_start(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText("No se pudo ejecutar Python para instalar los paquetes.")
            self._finished(-1, QProcess.ExitStatus.CrashExit)

    def _finished(self, code: int, _status=None) -> None:
        process, library = self._process, self._installing
        if process is None:
            return
        self._read_output()
        self._process = None
        process.deleteLater()
        importlib.invalidate_caches()  # que Python vea lo recién instalado sin reiniciar
        if code == 0 and self._steps:  # queda otro comando de pip por ejecutar
            self._run_next_step()
            return
        self._installing, self._steps = None, []
        self.buttons.setEnabled(True)
        self.listing.setEnabled(True)
        self._show_current(self.listing.currentItem())
        if code == 0 and library is not None and not library.missing:
            self.log.appendPlainText("Instalación terminada.")
        else:
            self.log.appendPlainText(
                f"La instalación no terminó bien (código {code}). Revisa el mensaje de arriba."
            )

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

    def reject(self) -> None:
        if self._process is None:  # a mitad de una instalación no se cierra
            super().reject()

    def selected_ids(self) -> list[str]:
        ids = []
        for row in range(self.listing.count()):
            item = self.listing.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids
