"""Nodos personalizados en la interfaz: diálogo de gestión y ventana principal."""

import json

import cv2
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QMessageBox

from palantir_nodes.customnodes.library import CustomNodeLibrary
from palantir_nodes.customnodes.spec import CustomNodeSpec
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui.custom_nodes_dialog import (
    TEMPLATES,
    CodeEdit,
    CustomNodesDialog,
    PythonHighlighter,
)
from palantir_nodes.ui.main_window import MainWindow

DOBLE = "def doble(x: int) -> int:\n    return x * 2\n"
TRIPLE = "def triple(x: int, y: int = 1) -> int:\n    return x * 3 + y\n"


def answer(monkeypatch, button):
    """Responde a todos los QMessageBox.question con ``button``."""
    asked = []

    def fake(parent, title, text, *args, **kwargs):
        asked.append(text)
        return button

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake))
    return asked


def silence_warnings(monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda p, t, text, *a, **k: shown.append(text))
    )
    return shown


@pytest.fixture(autouse=True)
def _discard_by_default(monkeypatch):
    """pytest-qt cierra los diálogos antes de limpiar fixtures: que no se queden esperando."""
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard),
    )


@pytest.fixture
def lib(tmp_path):
    return CustomNodeLibrary(load_builtin_nodes().copy(), tmp_path / "lib.json")


@pytest.fixture
def dialog(qtbot, lib):
    dlg = CustomNodesDialog(lib)
    qtbot.addWidget(dlg)
    return dlg


def settle(dlg):
    """Aplica de inmediato el análisis que la ventana retrasa mientras se escribe."""
    dlg._analysis_timer.stop()
    dlg.refresh_analysis()


def press(widget, key, text=""):
    widget.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
    )


# -- diálogo ---------------------------------------------------------------------------------


def test_empty_library_starts_with_a_new_node_from_the_first_template(dialog):
    assert dialog.current_id is None and dialog.dirty
    assert dialog.code.toPlainText() == next(iter(TEMPLATES.values()))
    assert dialog.btn_save.isEnabled() and not dialog.btn_delete.isEnabled()
    assert "umbral" in dialog.info.toPlainText() or "imagen" in dialog.info.toPlainText()


def test_every_template_is_valid_and_can_be_inserted(dialog):
    for name in TEMPLATES:
        dialog.insert_template(name)
        assert dialog.refresh_analysis().errors == [], name


def test_creating_a_node_through_the_form(dialog, lib):
    dialog.name_edit.setText("Doble")
    dialog.category.setCurrentText("Mis cálculos")
    dialog.code.setPlainText(DOBLE)
    dialog.description.setText("Multiplica por dos")
    settle(dialog)
    assert dialog.btn_save.isEnabled()
    assert dialog.save_current()
    spec = lib.get("custom.doble")
    assert spec and spec.category == "Mis cálculos" and spec.description == "Multiplica por dos"
    assert dialog.current_id == "custom.doble" and not dialog.dirty
    assert dialog.listing.count() == 1 and "Doble" in dialog.listing.item(0).text()
    assert "Mis cálculos" in [dialog.category.itemText(i) for i in range(dialog.category.count())]
    assert "x" in dialog.info.toPlainText()  # el análisis muestra el parámetro detectado


def test_invalid_code_disables_saving_and_explains_why(dialog, lib):
    dialog.name_edit.setText("Malo")
    dialog.code.setPlainText("def f(x: lista):\n    pass\n")
    settle(dialog)
    assert not dialog.btn_save.isEnabled()
    assert "lista" in dialog.info.toPlainText()
    assert not dialog.save_current() and not lib.entries
    dialog.code.setPlainText("def f(:\n")
    settle(dialog)
    assert (
        "línea" in dialog.info.toPlainText().lower()
        or "sintaxis" in dialog.info.toPlainText().lower()
    )
    assert not dialog.btn_save.isEnabled()


def test_duplicate_name_is_reported_and_not_saved(dialog, lib):
    dialog.name_edit.setText("Grayscale")
    dialog.code.setPlainText(DOBLE)
    settle(dialog)
    assert not dialog.btn_save.isEnabled()
    assert "Ya existe" in dialog.info.toPlainText()


def test_editing_an_existing_node_updates_it(dialog, lib):
    spec = lib.create("Doble", "X", DOBLE)
    dialog.refresh_list()
    dialog.select_entry(spec.id, confirm=False)
    assert dialog.name_edit.text() == "Doble" and dialog.code.toPlainText() == DOBLE
    assert not dialog.dirty and not dialog.btn_save.isEnabled()
    changes = []
    dialog.changed.connect(lambda c, r: changes.append((c, r)))
    dialog.code.setPlainText(TRIPLE)
    assert dialog.dirty and dialog.btn_save.isEnabled()
    assert dialog.save_current()
    assert lib.get(spec.id).code == TRIPLE and changes == [([spec.id], [])]
    assert [i.name for i in lib.registry.require(spec.id).inputs] == ["x", "y"]


def test_revert_discards_the_edits(dialog, lib):
    spec = lib.create("Doble", "X", DOBLE)
    dialog.select_entry(spec.id, confirm=False)
    dialog.name_edit.setText("Otro")
    dialog.code.setPlainText("basura")
    dialog.revert()
    assert dialog.name_edit.text() == "Doble" and dialog.code.toPlainText() == DOBLE
    assert not dialog.dirty


def test_unsaved_changes_ask_before_switching_or_creating(dialog, lib, monkeypatch):
    a, b = lib.create("Doble", "X", DOBLE), lib.create("Triple", "X", TRIPLE)
    dialog.refresh_list()
    dialog.select_entry(a.id, confirm=False)
    dialog.code.setPlainText(DOBLE + "# cambio\n")
    asked = answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    assert not dialog.select_entry(b.id) and dialog.current_id == a.id
    assert not dialog.new_entry() and dialog.current_id == a.id
    assert dialog.code.toPlainText().endswith("# cambio\n") and len(asked) == 2
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    assert dialog.select_entry(b.id) and dialog.current_id == b.id
    assert dialog.code.toPlainText() == TRIPLE


def test_closing_with_unsaved_changes_can_be_cancelled(dialog, lib, monkeypatch):
    dialog.code.setPlainText(DOBLE + "# cambio\n")
    answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    dialog.show()
    dialog.close()
    assert dialog.isVisible()
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    dialog.close()
    assert not dialog.isVisible()


def test_duplicate_button_creates_a_copy_and_selects_it(dialog, lib):
    spec = lib.create("Doble", "X", DOBLE)
    dialog.select_entry(spec.id, confirm=False)
    assert dialog.duplicate_current()
    assert dialog.current_id != spec.id and dialog.name_edit.text() == "Doble (copia)"
    assert len(lib.entries) == 2 and dialog.listing.count() == 2


def test_delete_asks_for_confirmation_and_reports_the_removal(dialog, lib, monkeypatch):
    spec = lib.create("Doble", "X", DOBLE)
    other = lib.create("Triple", "X", TRIPLE)
    dialog.select_entry(spec.id, confirm=False)
    removed = []
    dialog.changed.connect(lambda c, r: removed.append(r))
    answer(monkeypatch, QMessageBox.StandardButton.No)
    assert not dialog.delete_current() and spec.id in lib.entries
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    assert dialog.delete_current()
    assert spec.id not in lib.entries and spec.id not in lib.registry and removed == [[spec.id]]
    assert dialog.current_id == other.id  # pasa al siguiente


def test_deleting_the_last_node_leaves_a_blank_new_one(dialog, lib, monkeypatch):
    spec = lib.create("Doble", "X", DOBLE)
    dialog.select_entry(spec.id, confirm=False)
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog.delete_current()
    assert not lib.entries and dialog.current_id is None and dialog.listing.count() == 0


def test_usage_in_the_open_graph_is_mentioned_and_can_stop_the_save(qtbot, lib, monkeypatch):
    spec = lib.create("Doble", "X", DOBLE)
    dlg = CustomNodesDialog(lib, usage=lambda _id: 3)
    qtbot.addWidget(dlg)
    dlg.select_entry(spec.id, confirm=False)
    dlg.code.setPlainText(TRIPLE)
    asked = answer(monkeypatch, QMessageBox.StandardButton.No)
    assert not dlg.save_current() and lib.get(spec.id).code == DOBLE and "3 vez" in asked[0]
    asked = answer(monkeypatch, QMessageBox.StandardButton.Yes)
    assert dlg.save_current() and lib.get(spec.id).code == TRIPLE
    answer(monkeypatch, QMessageBox.StandardButton.No)
    assert not dlg.delete_current() and spec.id in lib.entries
    asked = answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dlg.delete_current()
    assert "3 vez" in asked[0] and spec.id not in lib.entries


def test_unwritable_library_still_applies_the_node_and_warns(qtbot, registry_blocked, monkeypatch):
    shown = silence_warnings(monkeypatch)
    dlg = CustomNodesDialog(registry_blocked)
    qtbot.addWidget(dlg)
    dlg.name_edit.setText("Doble")
    dlg.code.setPlainText(DOBLE)
    assert dlg.save_current()
    assert "custom.doble" in registry_blocked.registry and "no se pudo guardar" in shown[0]
    assert dlg.current_id == "custom.doble"


@pytest.fixture
def registry_blocked(tmp_path):
    blocker = tmp_path / "archivo"
    blocker.write_text("x")
    return CustomNodeLibrary(load_builtin_nodes().copy(), blocker / "lib.json")


def test_broken_entries_are_listed_and_can_be_fixed(qtbot, tmp_path):
    path = tmp_path / "lib.json"
    path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "custom.roto",
                        "label": "Roto",
                        "category": "X",
                        "code": "def f(x: lista): pass",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    lib = CustomNodeLibrary(load_builtin_nodes().copy(), path)
    lib.load()
    dlg = CustomNodesDialog(lib)
    qtbot.addWidget(dlg)
    assert dlg.current_id == "custom.roto" and "Tiene errores" in dlg.listing.item(0).toolTip()
    assert "lista" in dlg.info.toPlainText()
    dlg.code.setPlainText(DOBLE)
    assert dlg.save_current() and "custom.roto" in lib.registry and not lib.broken


def test_start_new_opens_on_a_blank_node_even_with_existing_ones(qtbot, lib):
    lib.create("Doble", "X", DOBLE)
    dlg = CustomNodesDialog(lib, start_new=True)
    qtbot.addWidget(dlg)
    assert dlg.current_id is None and dlg.name_edit.text().startswith("Nuevo nodo")


# -- editor de código -------------------------------------------------------------------------


def test_tab_inserts_four_spaces_and_shift_tab_removes_them(qtbot):
    edit = CodeEdit()
    qtbot.addWidget(edit)
    press(edit, Qt.Key.Key_Tab, "\t")
    assert edit.toPlainText() == "    "
    edit.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    )
    assert edit.toPlainText() == ""


def test_enter_keeps_the_indent_and_adds_one_after_a_colon(qtbot):
    edit = CodeEdit()
    qtbot.addWidget(edit)
    edit.setPlainText("def f(x):")
    cursor = edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit.setTextCursor(cursor)
    press(edit, Qt.Key.Key_Return, "\r")
    assert edit.toPlainText() == "def f(x):\n    "
    edit.insertPlainText("return 1")
    press(edit, Qt.Key.Key_Return, "\r")
    assert edit.toPlainText().endswith("return 1\n    ")


def test_highlighter_colours_keywords_and_strings(qtbot):
    edit = CodeEdit()
    qtbot.addWidget(edit)
    edit.setPlainText('def f():\n    return "hola"  # nota\n')
    assert isinstance(edit.highlighter, PythonHighlighter)
    layout = edit.document().firstBlock().layout()
    assert layout.formats()  # 'def' y el nombre tienen formato


# -- ventana principal ------------------------------------------------------------------------


def make_window(qtbot):
    window = MainWindow(load_builtin_nodes().copy())
    window._confirm_discard = lambda: True
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


@pytest.fixture
def win(qtbot):
    return make_window(qtbot)


def test_menu_and_shortcut_open_the_manager(win, monkeypatch):
    opened = []
    monkeypatch.setattr(CustomNodesDialog, "exec", lambda self: opened.append(self.current_id))
    assert win.action_custom_nodes.shortcut().toString() == "Ctrl+Shift+N"
    win.action_custom_nodes.trigger()
    win.action_new_custom_node.trigger()
    assert opened == [None, None]  # biblioteca vacía: siempre arranca en uno nuevo
    titles = [a.text() for a in win.menuBar().actions()]
    assert any("Nodos" in t for t in titles)


def test_preferences_button_and_add_menu_reach_the_manager(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "open_custom_nodes", lambda new=False: calls.append(new))
    win.view.new_custom_node_requested.emit()
    from palantir_nodes.ui.preferences_dialog import PreferencesDialog

    dlg = PreferencesDialog(win.prefs, win)
    dlg.custom_nodes_requested.connect(win.open_custom_nodes)
    dlg.custom_nodes_button.click()
    assert len(calls) == 2


def test_new_node_appears_in_the_search_and_can_be_added_and_run(win, qtbot, tmp_path):
    spec = win.custom_library.create("Doble", "Mis cálculos", DOBLE)
    assert [c.label for c in win.registry.search("dobl")] == ["Doble"]
    integer = win.graph.add_node("input.integer", params={"value": 21})
    node = win.graph.add_node(spec.id)
    win.graph.add_link(integer.id, "value", node.id, "x")
    assert node.id in win.scene.node_items
    win.runner.run()
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=10000)
    assert win.last_result.outputs[node.id]["result"] == 42


def test_editing_a_node_in_use_adapts_the_graph_and_clears_undo(win, monkeypatch):
    spec = win.custom_library.create("Doble", "X", DOBLE)
    a = win.graph.add_node(spec.id, input_values={"x": 5})
    win.graph.add_node(spec.id)
    assert win._count_nodes_of_type(spec.id) == 2
    shown = silence_warnings(monkeypatch)
    win.custom_library.update(CustomNodeSpec(spec.id, "Doble", "X", TRIPLE))
    win._on_custom_nodes_changed([spec.id], [])
    assert [i.name for i in win.graph.node(a.id).definition.inputs] == ["x", "y"]
    assert win.graph.node(a.id).input_values["x"] == 5
    assert not win.undo_stack.canUndo() and not win.undo_stack.isClean()
    assert shown == [] or "adaptó" in shown[0]


def test_removing_a_node_in_use_removes_it_from_the_graph(win, monkeypatch):
    spec = win.custom_library.create("Doble", "X", DOBLE)
    win.graph.add_node(spec.id)
    keep = win.graph.add_node("input.integer")
    win.custom_library.remove(spec.id)
    win._on_custom_nodes_changed([], [spec.id])
    assert set(win.graph.nodes) == {keep.id} and len(win.scene.node_items) == 1
    assert not win.undo_stack.canUndo()


def test_unrelated_changes_leave_the_undo_history_alone(win):
    spec = win.custom_library.create("Doble", "X", DOBLE)
    win.graph.add_node("input.integer")
    win.undo_stack.setClean()
    win._on_custom_nodes_changed([spec.id], [])  # no hay nodos de ese tipo en el grafo
    assert win.undo_stack.isClean()


# -- guardar y abrir proyectos ----------------------------------------------------------------


def save(win, path):
    return win._write_project(path)


def test_saved_project_embeds_only_the_custom_nodes_it_uses(win, tmp_path):
    used = win.custom_library.create("Doble", "X", DOBLE)
    win.custom_library.create("Triple", "X", TRIPLE)
    win.graph.add_node(used.id)
    path = tmp_path / "p.json"
    assert save(win, path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert [s["id"] for s in doc["custom_nodes"]] == [used.id]


def open_in_fresh_window(qtbot, path, monkeypatch, button):
    window = make_window(qtbot)
    asked = answer(monkeypatch, button)
    shown = silence_warnings(monkeypatch)
    ok = window.load_project(path)
    return window, ok, asked, shown


def project_with_custom_node(win, tmp_path):
    spec = win.custom_library.create("Doble", "X", DOBLE)
    win.graph.add_node(spec.id, input_values={"x": 4})
    path = tmp_path / "p.json"
    assert save(win, path)
    return spec, path


def test_opening_a_project_offers_to_import_its_nodes(qtbot, win, tmp_path, monkeypatch):
    spec, path = project_with_custom_node(win, tmp_path)
    cfg = tmp_path / "otra_config"
    cfg.mkdir()
    monkeypatch.setenv("PALANTIR_NODES_CONFIG_DIR", str(cfg))  # biblioteca vacía
    other, ok, asked, _ = open_in_fresh_window(
        qtbot, path, monkeypatch, QMessageBox.StandardButton.Yes
    )
    assert ok and len(asked) == 1 and "Doble" in asked[0] and "tus permisos" in asked[0]
    assert spec.id in other.custom_library.entries and spec.id in other.registry
    assert len(other.graph.nodes) == 1 and other.project.custom_nodes == []
    assert (cfg / "custom_nodes.json").exists()


def test_declining_the_import_keeps_the_nodes_hidden_but_not_lost(
    qtbot, win, tmp_path, monkeypatch
):
    spec, path = project_with_custom_node(win, tmp_path)
    cfg = tmp_path / "otra_config"
    cfg.mkdir()
    monkeypatch.setenv("PALANTIR_NODES_CONFIG_DIR", str(cfg))
    other, ok, _, _ = open_in_fresh_window(qtbot, path, monkeypatch, QMessageBox.StandardButton.No)
    assert ok and spec.id not in other.registry and not other.custom_library.entries
    assert not other.graph.nodes  # el nodo sigue en el archivo pero no se muestra
    assert [s["id"] for s in other.project.custom_nodes] == [spec.id]
    resaved = tmp_path / "re.json"
    assert save(other, resaved)
    doc = json.loads(resaved.read_text(encoding="utf-8"))
    assert [s["id"] for s in doc["custom_nodes"]] == [spec.id]  # sigue embebido
    assert doc["nodes"] and doc["nodes"][0]["type_id"] == spec.id  # y su nodo también


def test_no_question_when_the_library_already_has_the_node(qtbot, win, tmp_path, monkeypatch):
    spec, path = project_with_custom_node(win, tmp_path)
    other, ok, asked, _ = open_in_fresh_window(
        qtbot, path, monkeypatch, QMessageBox.StandardButton.No
    )
    assert ok and not asked and len(other.graph.nodes) == 1


def test_library_version_wins_over_the_projects_and_the_user_is_told(
    qtbot, win, tmp_path, monkeypatch
):
    spec, path = project_with_custom_node(win, tmp_path)
    win.custom_library.update(CustomNodeSpec(spec.id, "Doble", "X", TRIPLE))
    other, ok, asked, _ = open_in_fresh_window(
        qtbot, path, monkeypatch, QMessageBox.StandardButton.No
    )
    assert ok and not asked
    assert other.custom_library.get(spec.id).code == TRIPLE
    assert any("otra versión" in w for w in other.project.warnings)


def test_invalid_embedded_code_is_not_imported_and_is_reported(qtbot, win, tmp_path, monkeypatch):
    spec, path = project_with_custom_node(win, tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["custom_nodes"][0]["code"] = "def f(x: lista):\n    pass\n"
    path.write_text(json.dumps(doc), encoding="utf-8")
    cfg = tmp_path / "otra_config"
    cfg.mkdir()
    monkeypatch.setenv("PALANTIR_NODES_CONFIG_DIR", str(cfg))
    other, ok, _, _ = open_in_fresh_window(qtbot, path, monkeypatch, QMessageBox.StandardButton.Yes)
    assert ok and spec.id not in other.registry
    assert any("No se pudo importar" in w for w in other.project.warnings)
    assert [s["id"] for s in other.project.custom_nodes] == [spec.id]


def test_a_project_without_custom_nodes_never_asks(qtbot, win, tmp_path, monkeypatch):
    win.graph.add_node("input.integer")
    path = tmp_path / "p.json"
    assert save(win, path)
    other, ok, asked, _ = open_in_fresh_window(
        qtbot, path, monkeypatch, QMessageBox.StandardButton.No
    )
    assert ok and not asked and "custom_nodes" in json.loads(path.read_text(encoding="utf-8"))


def test_library_loaded_at_startup_registers_saved_nodes(qtbot, win, tmp_path, monkeypatch):
    win.custom_library.create("Doble", "X", DOBLE)
    again = make_window(qtbot)  # misma carpeta de configuración
    assert "custom.doble" in again.registry and again.custom_library.get("custom.doble")


def test_end_to_end_image_node_runs_in_the_window(win, qtbot, tmp_path):
    img = np.full((12, 16, 3), 100, np.uint8)
    src = tmp_path / "in.png"
    cv2.imencode(".png", img)[1].tofile(str(src))
    spec = win.custom_library.create(
        "Aclarar",
        "Mis filtros",
        "def aclarar(imagen: Image, cantidad: int = 50) -> Image:\n"
        "    return np.clip(imagen.astype(int) + cantidad, 0, 255).astype(np.uint8)\n",
    )
    load_node = win.graph.add_node("input.load_image", params={"path": str(src)})
    node = win.graph.add_node(spec.id, input_values={"cantidad": 30})
    win.graph.add_link(load_node.id, "image", node.id, "imagen")
    win.runner.run()
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=10000)
    out = win.last_result.outputs[node.id]["result"]
    assert out.shape == img.shape and int(out[0, 0, 0]) == 130
