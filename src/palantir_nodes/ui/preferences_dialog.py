"""Diálogo de preferencias de la aplicación."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.preferences import (
    PREVIEW_RATE_RANGE,
    ZOOM_SPEED_RANGE,
    Preferences,
    preferences_path,
)
from palantir_nodes.skins import SKINS
from palantir_nodes.ui.theme import Colors


class PreferencesDialog(QDialog):
    custom_nodes_requested = Signal()

    def __init__(self, prefs: Preferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferencias")
        self.setMinimumWidth(460)
        self._original = prefs

        self.reopen = QCheckBox("Reabrir el último proyecto al iniciar")
        self.grid = QCheckBox("Mostrar la cuadrícula del editor")
        self.zoom = QDoubleSpinBox()
        self.zoom.setRange(*ZOOM_SPEED_RANGE)
        self.zoom.setSingleStep(0.05)
        self.zoom.setDecimals(2)
        self.zoom.setToolTip("Factor de zoom por cada paso de la rueda del ratón")
        self.auto_run = QCheckBox("Ejecutar automáticamente al modificar el grafo")
        self.previews = QCheckBox("Mostrar previsualizaciones dentro de los nodos")
        self.rate = QSpinBox()
        self.rate.setRange(*PREVIEW_RATE_RANGE)
        self.rate.setSuffix(" por segundo")
        self.rate.setToolTip("Máximo de miniaturas por segundo durante el tiempo real")

        self.skin = QComboBox()
        for skin in SKINS.values():
            self.skin.addItem(skin.label, skin.id)
        self.skin_note = QLabel()
        self.skin_note.setWordWrap(True)
        self.skin_note.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        self.skin.currentIndexChanged.connect(self._update_skin_note)

        appearance = QGroupBox("Apariencia")
        form = QFormLayout(appearance)
        form.addRow("Skin", self.skin)
        form.addRow(self.skin_note)
        hint = QLabel("El skin cambia las barras, paneles y menús; los nodos conservan su aspecto.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        form.addRow(hint)

        general = QGroupBox("General")
        form = QFormLayout(general)
        form.addRow(self.reopen)

        editor = QGroupBox("Editor")
        form = QFormLayout(editor)
        form.addRow(self.grid)
        form.addRow("Velocidad del zoom", self.zoom)

        execution = QGroupBox("Ejecución (para proyectos nuevos)")
        form = QFormLayout(execution)
        form.addRow(self.auto_run)
        form.addRow(self.previews)
        form.addRow("Miniaturas en tiempo real", self.rate)
        note = QLabel(
            "Un proyecto guardado conserva su propio ajuste de Auto y de previsualizaciones."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        form.addRow(note)

        self.custom_nodes_button = QPushButton("Nodos personalizados…")
        self.custom_nodes_button.setToolTip("Crear, editar y borrar nodos escritos en Python")
        self.custom_nodes_button.clicked.connect(self.custom_nodes_requested.emit)
        general.layout().addRow(self.custom_nodes_button)

        location = QLabel(f"Se guardan en: {preferences_path()}")
        location.setWordWrap(True)
        location.setStyleSheet(f"color: {Colors.TEXT_DIM};")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self.restore_defaults
        )

        layout = QVBoxLayout(self)
        for widget in (appearance, general, editor, execution, location, buttons):
            layout.addWidget(widget)
        self._load(prefs)

    def _update_skin_note(self) -> None:
        skin = SKINS.get(self.skin.currentData())
        self.skin_note.setText(skin.description if skin else "")

    def _load(self, prefs: Preferences) -> None:
        self.skin.setCurrentIndex(max(0, self.skin.findData(prefs.skin)))
        self._update_skin_note()
        self.reopen.setChecked(prefs.reopen_last_project)
        self.grid.setChecked(prefs.show_grid)
        self.zoom.setValue(prefs.zoom_speed)
        self.auto_run.setChecked(prefs.auto_run_default)
        self.previews.setChecked(prefs.previews_default)
        self.rate.setValue(prefs.preview_rate_hz)

    def restore_defaults(self) -> None:
        """Vuelve a los valores de fábrica en el diálogo (se aplican al aceptar)."""
        self._load(Preferences(last_project=self._original.last_project))

    def preferences(self) -> Preferences:
        """Preferencias según el estado actual del diálogo."""
        return replace(
            self._original,
            reopen_last_project=self.reopen.isChecked(),
            skin=self.skin.currentData(),
            show_grid=self.grid.isChecked(),
            zoom_speed=round(self.zoom.value(), 2),
            auto_run_default=self.auto_run.isChecked(),
            previews_default=self.previews.isChecked(),
            preview_rate_hz=self.rate.value(),
        )
