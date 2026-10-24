"""Guardar, abrir y cambios sin guardar desde la ventana principal."""

import json
import os

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui.main_window import MainWindow

Buttons = QMessageBox.StandardButton


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes())
    window._confirm_discard = lambda: True  # los tests que lo necesitan lo restauran
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


@pytest.fixture
def dialogs(monkeypatch):
    """Sustituye los diálogos modales y registra lo que se muestra."""

    class Dialogs:
        save_path = ""
        open_path = ""
        question_answer = Buttons.Cancel
        questions = 0
        save_calls = 0

    d = Dialogs()
    d.critical, d.warning = [], []

    def get_save(*args, **kwargs):
        d.save_calls += 1
        return d.save_path, ""

    def question(*args):
        d.questions += 1
        return d.question_answer

    monkeypatch.setattr(QFileDialog, "getSaveFileName", get_save)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (d.open_path, ""))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: d.critical.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: d.warning.append(a[2]))
    monkeypatch.setattr(QMessageBox, "question", question)
    return d


def build_graph(win):
    ctl = win.controller
    load = ctl.add_node("input.load_image", (-200, 0))
    gray = ctl.add_node("image.grayscale", (50, 20))
    ctl.connect(load, "image", gray, "image")
    ctl.set_param(load, "mode", "grayscale")
    return load, gray


def test_save_as_then_save_reuses_the_path(win, dialogs, tmp_path):
    build_graph(win)
    assert "*" in win.windowTitle() and win.windowTitle().startswith("Sin título")
    dialogs.save_path = str(tmp_path / "mi proyecto")  # sin extensión: se añade .json
    assert win.save_project()
    saved = tmp_path / "mi proyecto.json"
    assert saved.exists() and win.project_path == saved
    assert win.undo_stack.isClean() and win.windowTitle().startswith("mi proyecto — ")

    win.controller.add_node("math.add", (0, 200))
    assert win.windowTitle().startswith("mi proyecto *")
    calls = dialogs.save_calls
    assert win.save_project()  # ya tiene ruta: no vuelve a preguntar
    assert dialogs.save_calls == calls and win.undo_stack.isClean()


def test_save_cancelled_keeps_project_dirty(win, dialogs):
    build_graph(win)
    dialogs.save_path = ""  # el usuario cancela el diálogo
    assert not win.save_project()
    assert not win.undo_stack.isClean() and win.project_path is None


def test_save_failure_is_reported_and_project_stays_dirty(win, dialogs, tmp_path):
    build_graph(win)
    dialogs.save_path = str(tmp_path / "no_hay_carpeta" / "p.json")
    assert not win.save_project()
    assert dialogs.critical and "No se pudo guardar" in dialogs.critical[0]
    assert not win.undo_stack.isClean() and win.project_path is None


def test_open_replaces_graph_and_restores_state(win, dialogs, tmp_path):
    build_graph(win)
    win.view.restore_state(1.5, (300.0, -40.0))
    win.action_auto.setChecked(False)
    dialogs.save_path = str(tmp_path / "p.json")
    assert win.save_project()
    expected_nodes = [n.to_dict() for n in win.graph.nodes.values()]

    # Se cambia todo y se reabre: el grafo se reemplaza por completo.
    win.action_auto.setChecked(True)
    win.controller.new_graph()
    win.controller.add_node("math.add", (0, 0))
    win.view.restore_state(0.5, (0.0, 0.0))
    dialogs.open_path = str(tmp_path / "p.json")
    win.open_project()

    assert [n.to_dict() for n in win.graph.nodes.values()] == expected_nodes
    assert len(win.graph.links) == 1 and len(win.scene.node_items) == 2
    assert win.undo_stack.isClean() and win.undo_stack.count() == 0
    assert win.view.zoom == pytest.approx(1.5)
    assert win.view.state()["center"] == pytest.approx(
        (300.0, -40.0), abs=2.5
    )  # redondeo a píxeles
    assert not win.action_auto.isChecked() and not win.runner.auto_run
    assert win.project_path == tmp_path / "p.json"
    assert not dialogs.warning


def test_open_cancelled_dialog_changes_nothing(win, dialogs):
    build_graph(win)
    dialogs.open_path = ""
    win.open_project()
    assert len(win.graph.nodes) == 2


def test_open_invalid_file_keeps_current_project(win, dialogs, tmp_path):
    build_graph(win)
    before = [n.to_dict() for n in win.graph.nodes.values()]
    bad = tmp_path / "malo.json"
    bad.write_text("{ no es json", encoding="utf-8")
    assert not win.load_project(bad)
    assert dialogs.critical and "no es JSON válido" in dialogs.critical[0]
    assert [n.to_dict() for n in win.graph.nodes.values()] == before
    assert not win.undo_stack.isClean()  # conserva sus cambios


def test_open_newer_format_is_refused_clearly(win, dialogs, tmp_path):
    path = tmp_path / "futuro.json"
    doc = {"format": "palantir-nodes", "version": 99, "nodes": [], "links": []}
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert not win.load_project(path)
    assert "más nuevo" in dialogs.critical[0]


def test_warnings_are_shown_and_unknown_nodes_survive_resave(win, dialogs, tmp_path):
    ghost = {"id": "g1", "type_id": "plugin.fantasma", "position": [0, 0], "params": {"x": 1}}
    doc = {
        "format": "palantir-nodes",
        "version": 1,
        "nodes": [
            {"id": "a", "type_id": "image.grayscale", "position": [10, 10]},
            {"id": "b", "type_id": "image.gaussian_blur", "params": {"ksize": "mal"}},
            ghost,
        ],
        "links": [
            {
                "id": "l",
                "src_node": "a",
                "src_socket": "image",
                "dst_node": "b",
                "dst_socket": "image",
            },
            {
                "id": "gl",
                "src_node": "g1",
                "src_socket": "out",
                "dst_node": "a",
                "dst_socket": "image",
            },
        ],
    }
    path = tmp_path / "con_avisos.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert win.load_project(path)
    assert len(win.scene.node_items) == 2 and len(win.graph.links) == 1
    assert dialogs.warning and "plugin.fantasma" in dialogs.warning[0]

    win.controller.add_node("math.add", (0, 0))
    assert win.save_project()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert ghost in saved["nodes"] and any(link["id"] == "gl" for link in saved["links"])
    assert len(saved["nodes"]) == 4


def test_unsaved_changes_prompt_on_new_project(win, dialogs, tmp_path):
    del win._confirm_discard  # usa la comprobación real
    build_graph(win)

    dialogs.question_answer = Buttons.Cancel
    win.new_project()
    assert dialogs.questions == 1 and len(win.graph.nodes) == 2  # canceló: nada cambia

    dialogs.question_answer = Buttons.Save
    dialogs.save_path = str(tmp_path / "guardado.json")
    win.new_project()
    assert (tmp_path / "guardado.json").exists() and not win.graph.nodes
    assert win.project_path is None and win.windowTitle().startswith("Sin título —")

    build_graph(win)
    dialogs.question_answer = Buttons.Discard
    win.new_project()
    assert dialogs.questions == 3 and not win.graph.nodes and not win.undo_stack.count()
    win._confirm_discard = lambda: True


def test_save_in_prompt_that_fails_cancels_the_operation(win, dialogs):
    del win._confirm_discard
    build_graph(win)
    dialogs.question_answer = Buttons.Save
    dialogs.save_path = ""  # elige Guardar pero cancela el diálogo de archivo
    win.new_project()
    assert len(win.graph.nodes) == 2  # no se descartó nada
    win._confirm_discard = lambda: True


def test_clean_project_does_not_prompt(win, dialogs, tmp_path):
    del win._confirm_discard
    build_graph(win)
    dialogs.save_path = str(tmp_path / "p.json")
    win.save_project()
    win.new_project()
    assert dialogs.questions == 0
    win._confirm_discard = lambda: True


def test_new_project_resets_path_and_title(win, dialogs, tmp_path):
    build_graph(win)
    dialogs.save_path = str(tmp_path / "p.json")
    win.save_project()
    assert win.project_path is not None
    win.new_project()
    assert win.project_path is None and win.windowTitle().startswith("Sin título —")


def test_open_stops_realtime_and_releases_the_video(qtbot, win, dialogs, tmp_path, video_path):
    ctl = win.controller
    load = ctl.add_node("input.load_video", (0, 0))
    view = ctl.add_node("output.video_viewer", (200, 0))
    ctl.set_param(load, "path", video_path)
    ctl.set_param(load, "loop", True)
    ctl.connect(load, "image", view, "image")
    win.runner.auto_run = False
    dialogs.save_path = str(tmp_path / "video.json")
    assert win.save_project()

    win.action_run.trigger()
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=5000)
    assert win.runner.realtime_active
    assert win.load_project(tmp_path / "video.json")
    assert not win.runner.realtime_active and len(win.graph.nodes) == 2
    os.remove(video_path)  # nada quedó abierto


def test_saved_file_is_valid_json_with_expected_shape(win, dialogs, tmp_path):
    build_graph(win)
    dialogs.save_path = str(tmp_path / "forma.json")
    win.save_project()
    doc = json.loads((tmp_path / "forma.json").read_text(encoding="utf-8"))
    assert doc["format"] == "palantir-nodes" and doc["version"] == 1
    assert len(doc["nodes"]) == 2 and len(doc["links"]) == 1
    assert doc["meta"]["name"] == "forma" and "zoom" in doc["editor"]
