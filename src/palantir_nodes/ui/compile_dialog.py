"""Diálogo para compilar el grafo a un ejecutable (.exe) con PyInstaller."""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.build import compiler
from palantir_nodes.ui.libraries_dialog import can_install, pip_command
from palantir_nodes.ui.theme import Colors


class CompileDialog(QDialog):
    """Escribe el script en una carpeta temporal, instala PyInstaller si falta y compila."""

    def __init__(
        self,
        code: str,
        parent: QWidget | None = None,
        *,
        name: str = "grafo",
        folder: str = "",
        search_paths: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compilar a ejecutable")
        self.resize(720, 520)
        self._code = code
        self._search_paths = list(search_paths or [])
        self._steps: list[tuple[str, list[str], str]] = []
        self._process: QProcess | None = None
        self._temp: Path | None = None
        self.result_path: Path | None = None

        intro = QLabel(
            "Convierte el grafo en un programa que se ejecuta sin la aplicación ni Python "
            "(solo en este sistema operativo). Usa PyInstaller; puede tardar uno o dos minutos y "
            "el archivo pesa decenas de MB porque incluye OpenCV."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        self.name_edit = QLineEdit(compiler.safe_name(name))
        self.folder_edit = QLineEdit(folder or str(Path.home() / "Palantir Nodes"))
        self.btn_browse = QPushButton("Elegir…")
        self.onefile = QCheckBox("Un solo archivo (más cómodo; tarda más en abrir)")
        self.onefile.setChecked(True)
        self.console = QCheckBox("Mostrar la consola (para ver mensajes y errores)")
        self.console.setChecked(True)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Aquí aparece el avance de la compilación")
        self.btn_compile = QPushButton("Compilar")
        self.btn_open = QPushButton("Abrir carpeta")
        self.btn_open.setEnabled(False)
        self.btn_close = QPushButton("Cerrar")

        row = QHBoxLayout()
        row.addWidget(self.folder_edit, 1)
        row.addWidget(self.btn_browse)
        form = QFormLayout()
        form.addRow("Nombre", self.name_edit)
        form.addRow("Carpeta de salida", row)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status, 1)
        for button in (self.btn_open, self.btn_compile, self.btn_close):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.onefile)
        layout.addWidget(self.console)
        layout.addWidget(self.log, 1)
        layout.addLayout(buttons)

        self.btn_browse.clicked.connect(self.choose_folder)
        self.btn_compile.clicked.connect(self.compile)
        self.btn_open.clicked.connect(self.open_folder)
        self.btn_close.clicked.connect(self.close)
        self._refresh_status()

    # -- estado -------------------------------------------------------------------------------

    def _refresh_status(self) -> None:
        if not can_install():
            self.status.setText("Esta versión empaquetada no puede compilar.")
            self.btn_compile.setEnabled(False)
        elif compiler.pyinstaller_available():
            self.status.setText("PyInstaller está instalado.")
        else:
            self.status.setText("Falta PyInstaller: se instalará con pip al compilar.")

    @property
    def running(self) -> bool:
        return self._process is not None

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Carpeta de salida", self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)

    def open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder_edit.text()))

    # -- compilación ----------------------------------------------------------------------------

    def compile(self) -> bool:
        """Inicia la compilación (``False`` si no se puede o el usuario cancela)."""
        if self.running or not can_install():
            return False
        name = compiler.safe_name(self.name_edit.text())
        self.name_edit.setText(name)
        folder = Path(self.folder_edit.text().strip() or ".")
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Compilar", f"No se pudo crear la carpeta de salida:\n{exc}")
            return False
        steps: list[tuple[str, list[str], str]] = []
        if not compiler.pyinstaller_available():
            answer = QMessageBox.question(
                self,
                "Instalar PyInstaller",
                "Hace falta PyInstaller. Se descargará e instalará de PyPI con pip en el Python "
                f"de la aplicación:\n{sys.executable} -m pip install pyinstaller\n\n¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            program, args = pip_command(["pyinstaller"])
            steps.append((program, args, "install"))
        self._temp = Path(tempfile.mkdtemp(prefix="palantir_build_"))
        script = self._temp / f"{name}.py"
        script.write_text(self._code, encoding="utf-8", newline="\n")
        program, args = compiler.pyinstaller_command(
            script,
            name,
            folder,
            self._temp,
            onefile=self.onefile.isChecked(),
            console=self.console.isChecked(),
            search_paths=self._search_paths,
            collect=compiler.packages_to_collect(self._code),
        )
        steps.append((program, args, "build"))
        self._steps = steps
        self.result_path = None
        self.log.clear()
        self._set_busy(True)
        self._run_next()
        return True

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.btn_compile, self.name_edit, self.folder_edit, self.btn_browse):
            widget.setEnabled(not busy)
        self.onefile.setEnabled(not busy)
        self.console.setEnabled(not busy)
        self.btn_close.setEnabled(not busy)

    def _run_next(self) -> None:
        program, args, _kind = self._steps[0]
        self.log.appendPlainText(f"$ {program} {' '.join(args)}")
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._failed_to_start)
        self._process = process
        process.start(program, args)

    def _read_output(self) -> None:
        if self._process is not None:
            text = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
            if text.strip():
                self.log.appendPlainText(text.rstrip("\r\n"))

    def _failed_to_start(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText("No se pudo ejecutar Python para compilar.")
            self._finished(-1, QProcess.ExitStatus.CrashExit)

    def _finished(self, code: int, _status=None) -> None:
        process = self._process
        if process is None:
            return
        self._read_output()
        self._process = None
        process.deleteLater()
        kind = self._steps.pop(0)[2]
        importlib.invalidate_caches()  # PyInstaller recién instalado
        if code == 0 and self._steps:
            self._run_next()
            return
        self._steps = []
        if code == 0 and kind == "build":
            self.result_path = compiler.executable_path(
                self.folder_edit.text().strip(), self.name_edit.text(), self.onefile.isChecked()
            )
            self.log.appendPlainText(f"Listo: {self.result_path}")
            self.status.setText("Compilación terminada.")
            self.btn_open.setEnabled(True)
        else:
            self.log.appendPlainText(f"La compilación no terminó bien (código {code}).")
            self.status.setText("La compilación falló: revisa el registro.")
        self._cleanup()
        self._set_busy(False)

    def _cleanup(self) -> None:
        if self._temp is not None:
            shutil.rmtree(self._temp, ignore_errors=True)
            self._temp = None

    def reject(self) -> None:
        if not self.running:
            self._cleanup()
            super().reject()

    def closeEvent(self, event) -> None:
        if self.running:
            event.ignore()
        else:
            self._cleanup()
            event.accept()
