"""Preferencias: archivo, validación, diálogo y efecto real en la aplicación."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.preferences import (
    CONFIG_DIR_ENV,
    PREVIEW_RATE_RANGE,
    ZOOM_SPEED_RANGE,
    Preferences,
    config_dir,
    load_preferences,
    preferences_path,
    save_preferences,
)
from palantir_nodes.ui.main_window import MainWindow
from palantir_nodes.ui.preferences_dialog import PreferencesDialog
from palantir_nodes.ui.theme import Colors

# -- archivo y validación (sin Qt) -------------------------------------------------------


def test_defaults_roundtrip_through_file(tmp_path):
    path = tmp_path / "p.json"
    prefs = Preferences(
        reopen_last_project=True,
        last_project="C:/proyectos/ñandú.json",
        show_grid=False,
        zoom_speed=1.3,
        auto_run_default=False,
        previews_default=False,
        preview_rate_hz=24,
    )
    save_preferences(prefs, path)
    loaded, warnings = load_preferences(path)
    assert loaded == prefs and not warnings
    assert "ñandú" in path.read_text(encoding="utf-8")


def test_missing_file_gives_defaults_without_warnings(tmp_path):
    prefs, warnings = load_preferences(tmp_path / "no_existe.json")
    assert prefs == Preferences() and not warnings


def test_config_dir_follows_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / "mi_config"))
    assert config_dir() == tmp_path / "mi_config"
    assert preferences_path() == tmp_path / "mi_config" / "preferences.json"
    monkeypatch.delenv(CONFIG_DIR_ENV)
    assert "PalantirNodes" in str(config_dir()) or "palantir-nodes" in str(config_dir())


def test_save_creates_missing_folders(tmp_path):
    path = tmp_path / "a" / "b" / "p.json"
    save_preferences(Preferences(), path)
    assert path.exists() and not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize(
    "content",
    [b"", b"{ no es json", b"\xff\xfe\x00", b"[1, 2]", b'"texto"', b"null"],
)
def test_corrupt_files_fall_back_to_defaults_with_a_warning(tmp_path, content):
    path = tmp_path / "p.json"
    path.write_bytes(content)
    prefs, warnings = load_preferences(path)
    assert prefs == Preferences() and len(warnings) == 1


def test_invalid_values_are_replaced_individually(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(
        json.dumps(
            {
                "show_grid": "sí",
                "zoom_speed": "rápido",
                "preview_rate_hz": [5],
                "reopen_last_project": True,  # este sí es válido y se conserva
                "last_project": 5,
                "desconocida": 1,
            }
        ),
        encoding="utf-8",
    )
    prefs, warnings = load_preferences(path)
    assert prefs == Preferences(reopen_last_project=True)
    assert len(warnings) == 4  # grid, zoom, rate, last_project; la desconocida se ignora


def test_out_of_range_numbers_are_clamped(tmp_path):
    prefs, warnings = Preferences.from_dict({"zoom_speed": 9.0, "preview_rate_hz": 1000})
    assert (
        prefs.zoom_speed == ZOOM_SPEED_RANGE[1] and prefs.preview_rate_hz == PREVIEW_RATE_RANGE[1]
    )
    prefs, _ = Preferences.from_dict({"zoom_speed": 0.1, "preview_rate_hz": -3})
    assert (
        prefs.zoom_speed == ZOOM_SPEED_RANGE[0] and prefs.preview_rate_hz == PREVIEW_RATE_RANGE[0]
    )
    assert len(warnings) == 2


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), None])
def test_non_numeric_special_values_are_rejected(bad):
    prefs, warnings = Preferences.from_dict({"zoom_speed": bad, "preview_rate_hz": bad})
    assert prefs == Preferences() and len(warnings) == 2


def test_integer_rate_is_rounded_and_float_zoom_accepts_ints():
    prefs, _ = Preferences.from_dict({"preview_rate_hz": 12.6, "zoom_speed": 1})
    assert prefs.preview_rate_hz == 13 and isinstance(prefs.preview_rate_hz, int)
    assert prefs.zoom_speed == ZOOM_SPEED_RANGE[0] and isinstance(prefs.zoom_speed, float)


# -- diálogo -----------------------------------------------------------------------------


def test_dialog_shows_current_values_and_returns_edits(qtbot):
    prefs = Preferences(show_grid=False, zoom_speed=1.4, preview_rate_hz=8, last_project="x.json")
    dialog = PreferencesDialog(prefs)
    qtbot.addWidget(dialog)
    assert not dialog.grid.isChecked() and dialog.zoom.value() == 1.4 and dialog.rate.value() == 8
    assert dialog.preferences() == prefs  # sin tocar nada no cambia nada

    dialog.reopen.setChecked(True)
    dialog.grid.setChecked(True)
    dialog.zoom.setValue(1.25)
    dialog.auto_run.setChecked(False)
    dialog.previews.setChecked(False)
    dialog.rate.setValue(20)
    assert dialog.preferences() == Preferences(
        reopen_last_project=True,
        last_project="x.json",  # el último proyecto no se edita aquí y se conserva
        show_grid=True,
        zoom_speed=1.25,
        auto_run_default=False,
        previews_default=False,
        preview_rate_hz=20,
    )


def test_dialog_limits_and_restore_defaults(qtbot):
    dialog = PreferencesDialog(Preferences(zoom_speed=1.4, show_grid=False, last_project="x"))
    qtbot.addWidget(dialog)
    dialog.zoom.setValue(99)
    dialog.rate.setValue(-5)
    assert (
        dialog.zoom.value() == ZOOM_SPEED_RANGE[1] and dialog.rate.value() == PREVIEW_RATE_RANGE[0]
    )
    dialog.restore_defaults()
    assert dialog.preferences() == Preferences(last_project="x")


# -- integración con la ventana ----------------------------------------------------------


def make_window(qtbot):
    window = MainWindow(load_builtin_nodes())
    window._confirm_discard = lambda: True
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


@pytest.fixture
def win(qtbot):
    return make_window(qtbot)


def stored():
    return json.loads(preferences_path().read_text(encoding="utf-8"))["preferences"]


def test_preferences_action_opens_dialog_and_applies_on_accept(win, monkeypatch):
    chosen = replace(win.prefs, show_grid=False, zoom_speed=1.3, preview_rate_hz=9)

    def fake_exec(self):
        self.grid.setChecked(False)
        self.zoom.setValue(1.3)
        self.rate.setValue(9)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PreferencesDialog, "exec", fake_exec)
    win.action_prefs.trigger()
    assert win.prefs == chosen
    assert not win.view.grid_visible and win.view.zoom_step == 1.3
    assert win.runner.preview_rate_hz == 9
    assert stored()["show_grid"] is False and stored()["preview_rate_hz"] == 9


def test_cancelling_the_dialog_changes_nothing(win, monkeypatch):
    before = win.prefs
    monkeypatch.setattr(
        PreferencesDialog,
        "exec",
        lambda self: self.grid.setChecked(False) or QDialog.DialogCode.Rejected,
    )
    win.action_prefs.trigger()
    assert win.prefs == before and win.view.grid_visible
    assert not preferences_path().exists()


def test_grid_visibility_is_really_drawn_or_not(win):
    def render() -> QImage:
        image = QImage(win.view.viewport().size(), QImage.Format.Format_RGB32)
        win.view.viewport().render(image, QPoint(0, 0))
        return image

    def distinct_colors(image: QImage) -> set[int]:
        return {
            image.pixel(x, y)
            for x in range(0, image.width(), 3)
            for y in range(0, image.height(), 3)
        }

    background = int(Colors.EDITOR_BG.lstrip("#"), 16) | 0xFF000000
    assert len(distinct_colors(render())) > 1  # líneas de la cuadrícula
    win.set_preferences(replace(win.prefs, show_grid=False))
    assert distinct_colors(render()) == {background}  # solo el color de fondo
    win.set_preferences(replace(win.prefs, show_grid=True))
    assert len(distinct_colors(render())) > 1


def test_zoom_speed_changes_the_wheel_step(win):
    class Wheel:
        def __init__(self, delta):
            self._delta = delta

        def angleDelta(self):
            return QPoint(0, self._delta)

    win.view.resetTransform()
    win.set_preferences(replace(win.prefs, zoom_speed=1.5))
    win.view.wheelEvent(Wheel(120))
    assert win.view.zoom == pytest.approx(1.5)
    win.view.resetTransform()
    win.set_preferences(replace(win.prefs, zoom_speed=1.05))
    win.view.wheelEvent(Wheel(120))
    assert win.view.zoom == pytest.approx(1.05)


def test_new_project_uses_the_default_run_and_preview_settings(win, tmp_path, monkeypatch):
    win.set_preferences(replace(win.prefs, auto_run_default=False, previews_default=False))
    assert win.action_auto.isChecked()  # el proyecto actual no cambia
    win.new_project()
    assert not win.action_auto.isChecked() and not win.runner.auto_run
    assert not win.action_previews.isChecked() and not win.runner.preview_enabled
    assert win.project.auto_run is False and win.project.previews is False

    path = tmp_path / "p.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    win.controller.add_node("image.grayscale", (0, 0))
    assert win.save_project()
    saved = json.loads(path.read_text(encoding="utf-8"))["settings"]
    assert saved == {"auto_run": False, "previews": False}


def test_opening_a_project_overrides_the_defaults(win, tmp_path):
    from palantir_nodes.persistence import ProjectData, dump, write_project

    path = tmp_path / "p.json"
    write_project(path, dump(win.graph, ProjectData(auto_run=True, previews=True), ""))
    win.set_preferences(replace(win.prefs, auto_run_default=False, previews_default=False))
    win.new_project()
    assert win.load_project(path)
    assert win.action_auto.isChecked() and win.action_previews.isChecked()


def test_new_window_starts_with_stored_preferences(qtbot):
    save_preferences(
        Preferences(show_grid=False, zoom_speed=1.4, auto_run_default=False, preview_rate_hz=7)
    )
    window = make_window(qtbot)
    assert not window.view.grid_visible and window.view.zoom_step == 1.4
    assert not window.action_auto.isChecked() and not window.runner.auto_run
    assert window.runner.preview_rate_hz == 7


def test_corrupt_preferences_file_does_not_stop_the_app(qtbot):
    preferences_path().parent.mkdir(parents=True, exist_ok=True)
    preferences_path().write_text("{ roto", encoding="utf-8")
    window = make_window(qtbot)
    assert window.prefs == Preferences() and window.view.grid_visible
    assert "No se pudieron leer las preferencias" in window.statusBar().currentMessage()


def test_last_project_is_remembered_and_reopened(qtbot, win, tmp_path, monkeypatch):
    win.controller.add_node("image.grayscale", (10, 20))
    path = tmp_path / "ultimo.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    assert win.save_project()
    assert stored()["last_project"] == str(path)

    # Por defecto no se reabre: es opcional.
    fresh = make_window(qtbot)
    assert not fresh.reopen_last_project() and not fresh.graph.nodes

    fresh.set_preferences(replace(fresh.prefs, reopen_last_project=True))
    again = make_window(qtbot)
    assert again.reopen_last_project()
    assert len(again.graph.nodes) == 1 and again.project_path == path


def test_reopen_last_project_ignores_missing_file(qtbot, win, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: shown.append(a))
    win.set_preferences(
        replace(win.prefs, reopen_last_project=True, last_project=str(Path("no_existe.json")))
    )
    assert not win.reopen_last_project() and not shown and not win.graph.nodes


def test_opening_a_project_also_updates_the_last_project(win, tmp_path):
    from palantir_nodes.persistence import ProjectData, dump, write_project

    path = tmp_path / "abierto.json"
    write_project(path, dump(win.graph, ProjectData(), ""))
    assert win.load_project(path)
    assert stored()["last_project"] == str(path)


def test_unwritable_config_does_not_crash_and_warns_on_explicit_save(win, tmp_path, monkeypatch):
    blocker = tmp_path / "es_un_archivo"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv(CONFIG_DIR_ENV, str(blocker))  # no se puede crear una carpeta dentro
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    assert not win.set_preferences(replace(win.prefs, show_grid=False))
    assert warnings and "No se pudieron guardar las preferencias" in warnings[0]
    assert not win.view.grid_visible  # aun así se aplican en esta sesión
    win._remember_project(tmp_path / "x.json")  # guardar el "último proyecto" no molesta
    assert len(warnings) == 1


def test_preview_rate_reaches_a_running_realtime_session(qtbot, win, tmp_path):
    import cv2
    import numpy as np

    video = tmp_path / "v.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (64, 48))
    for _ in range(5):
        writer.write(np.full((48, 64, 3), 80, np.uint8))
    writer.release()
    ctl = win.controller
    load_id = ctl.add_node("input.load_video", (0, 0))
    view = ctl.add_node("output.video_viewer", (300, 0))
    ctl.set_param(load_id, "path", str(video))
    ctl.set_param(load_id, "loop", True)
    ctl.connect(load_id, "image", view, "image")
    win.set_preferences(replace(win.prefs, preview_rate_hz=10))
    win.action_run.trigger()
    assert win.runner._rt_worker._preview_interval == pytest.approx(0.1)
    win.set_preferences(replace(win.prefs, preview_rate_hz=25))
    assert win.runner._rt_worker._preview_interval == pytest.approx(0.04)
    win.runner.stop_realtime(wait=True)


def test_standard_qt_buttons_are_translated_to_spanish(qtbot):
    from PySide6.QtWidgets import QDialogButtonBox

    from palantir_nodes.app import install_spanish_qt_translations

    app = QApplication.instance()
    assert install_spanish_qt_translations(app)
    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
    )
    qtbot.addWidget(box)
    texts = {b.text().replace("&", "") for b in box.buttons()}
    assert "Cancelar" in texts and "Guardar" in texts
