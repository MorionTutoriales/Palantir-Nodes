"""Rutas de importación: módulos propios del usuario dentro de los nodos personalizados."""

import json
import subprocess
import sys

import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QDialog, QFileDialog

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.graph import Graph
from palantir_nodes.customnodes.analysis import analyze, imported_modules
from palantir_nodes.customnodes.library import CustomNodeLibrary
from palantir_nodes.customnodes.paths import (
    applied_paths,
    apply_import_paths,
    missing_paths,
    normalize,
)
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.preferences import Preferences, load_preferences, preferences_path
from palantir_nodes.ui.custom_nodes_dialog import CustomNodesDialog
from palantir_nodes.ui.import_paths_dialog import ImportPathsDialog
from palantir_nodes.ui.main_window import MainWindow

MODULE = "mi_modulo_de_prueba_xyz"
USER_CODE = f"""import {MODULE}


def usar(x: int) -> int:
    return {MODULE}.doble(x) + 1
"""


@pytest.fixture(autouse=True)
def clean_paths():
    """Cada prueba deja sys.path y los módulos importados como los encontró."""
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    yield
    apply_import_paths([])
    sys.path[:] = saved_path
    for name in set(sys.modules) - saved_modules:
        if name.startswith(MODULE):
            del sys.modules[name]


@pytest.fixture
def libs(tmp_path):
    folder = tmp_path / "mis_libs"
    folder.mkdir()
    (folder / f"{MODULE}.py").write_text("def doble(x):\n    return x * 2\n", encoding="utf-8")
    return folder


@pytest.fixture
def registry():
    return load_builtin_nodes().copy()


def run(graph):
    return Executor().run(ExecutionPlan.from_graph(graph), ExecContext())


# -- sys.path -----------------------------------------------------------------------------------------


def test_paths_are_appended_at_the_end_and_replaced_on_the_next_call(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    first = apply_import_paths([str(a), str(b)])
    assert first == [str(a), str(b)] and sys.path[-2:] == [
        str(a),
        str(b),
    ]  # al final: no tapan nada
    assert applied_paths() == first
    apply_import_paths([str(b)])
    assert str(a) not in sys.path and sys.path.count(str(b)) == 1
    apply_import_paths([])
    assert str(b) not in sys.path and applied_paths() == []


def test_folders_already_in_sys_path_are_not_taken_over_or_removed(tmp_path):
    mine = str(tmp_path / "existente")
    sys.path.append(mine)
    assert apply_import_paths([mine]) == []  # ya estaba: no es de la aplicación
    apply_import_paths([])
    assert mine in sys.path


def test_paths_are_normalised_and_repeats_ignored(tmp_path):
    messy = str(tmp_path / "x" / ".." / "y")
    assert apply_import_paths([messy, str(tmp_path / "y"), "   "]) == [str(tmp_path / "y")]
    assert normalize("  ~/libs  ").endswith("libs") and "~" not in normalize("~/libs")


def test_missing_paths(tmp_path, libs):
    assert missing_paths([str(libs), str(tmp_path / "no_existe")]) == [str(tmp_path / "no_existe")]


# -- preferencias -------------------------------------------------------------------------------------


def test_import_paths_are_saved_and_loaded(tmp_path):
    prefs = Preferences(import_paths=["C:/libs", "D:/otras ñ"])
    data = prefs.to_dict()
    loaded, warnings = Preferences.from_dict(json.loads(json.dumps(data)))
    assert loaded.import_paths == ["C:/libs", "D:/otras ñ"] and not warnings


def test_invalid_import_paths_are_cleaned_with_a_warning():
    loaded, warnings = Preferences.from_dict({"import_paths": ["a", "a", "", 5, None, " b "]})
    assert loaded.import_paths == ["a", "b"] and "omitieron" in warnings[0]
    loaded, warnings = Preferences.from_dict({"import_paths": "C:/libs"})
    assert loaded.import_paths == [] and "import_paths" in warnings[0]
    many, _ = Preferences.from_dict({"import_paths": [f"p{i}" for i in range(80)]})
    assert len(many.import_paths) == 50
    assert (
        Preferences().import_paths == []
        and Preferences().import_paths is not Preferences().import_paths
    )


# -- análisis -----------------------------------------------------------------------------------------


def messages(analysis):
    return [str(w) for w in analysis.warnings]


def test_unknown_modules_are_reported_with_the_line_and_known_ones_are_not():
    code = "import os\nimport numpy as np\nimport modulo_que_no_existe_abc\n\n\ndef f(x: int) -> int:\n    return x\n"
    found = messages(analyze(code))
    assert len(found) == 1 and "modulo_que_no_existe_abc" in found[0] and "línea 3" in found[0]
    assert "Rutas de importación" in found[0]
    assert analyze(code).ok  # un aviso, no un error: se puede guardar


@pytest.mark.parametrize(
    "line,module",
    [
        ("from fantasma_uno import algo", "fantasma_uno"),
        ("import fantasma_dos.sub.mod", "fantasma_dos"),
        ("import os, fantasma_tres", "fantasma_tres"),
    ],
)
def test_import_forms_report_the_top_level_module(line, module):
    found = messages(analyze(f"{line}\n\n\ndef f(x: int) -> int:\n    return x\n"))
    assert len(found) == 1 and f"'{module}'" in found[0]


def test_imports_inside_functions_count_and_relative_or_stdlib_ones_do_not():
    code = (
        "from . import hermano\nfrom json import loads\nimport math, os.path\n\n\n"
        "def f(x: int) -> int:\n    import fantasma_cuatro\n    return x\n"
    )
    assert [m for m, _ in imported_modules(__import__("ast").parse(code))] == [
        "json",
        "math",
        "os",
        "fantasma_cuatro",
    ]
    found = messages(analyze(code))
    assert len(found) == 1 and "fantasma_cuatro" in found[0]


def test_a_folder_in_the_import_paths_resolves_the_warning(libs):
    code = USER_CODE
    assert any(MODULE in w for w in messages(analyze(code)))
    apply_import_paths([str(libs)])
    assert not any(MODULE in w for w in messages(analyze(code)))


def test_analysing_never_runs_the_imported_module(tmp_path):
    marker = tmp_path / "ejecutado.txt"
    folder = tmp_path / "libs"
    folder.mkdir()
    (folder / f"{MODULE}_efecto.py").write_text(
        f"open({str(marker)!r}, 'w').write('x')\n", encoding="utf-8"
    )
    apply_import_paths([str(folder)])
    result = analyze(f"import {MODULE}_efecto\n\n\ndef f(x: int) -> int:\n    return x\n")
    assert result.ok and not result.warnings and not marker.exists()


# -- ejecución -----------------------------------------------------------------------------------------


def custom_graph(registry, tmp_path):
    lib = CustomNodeLibrary(registry, tmp_path / "lib.json")
    spec = lib.create("Usa mi módulo", "Mis nodos", USER_CODE)
    g = Graph(registry)
    node = g.add_node(spec.id, input_values={"x": 5})
    return g, node


def test_node_fails_with_a_hint_until_the_folder_is_added_then_works(registry, tmp_path, libs):
    g, node = custom_graph(registry, tmp_path)
    error = run(g).errors[node.id]
    assert "ModuleNotFoundError" in error and "Rutas de importación" in error and "línea 1" in error
    apply_import_paths([str(libs)])
    result = run(g)
    assert result.ok and result.outputs[node.id]["result"] == 11


def test_removing_the_folder_makes_a_new_node_fail_again(registry, tmp_path, libs):
    apply_import_paths([str(libs)])
    g, node = custom_graph(registry, tmp_path)
    assert run(g).outputs[node.id]["result"] == 11
    apply_import_paths([])
    sys.modules.pop(MODULE, None)  # como en una sesión nueva
    lib = CustomNodeLibrary(registry, tmp_path / "otra.json")
    spec = lib.create("Otro", "Mis nodos", USER_CODE.replace("usar", "usar2"))
    g2 = Graph(registry)
    other = g2.add_node(spec.id, input_values={"x": 1})
    assert "ModuleNotFoundError" in run(g2).errors[other.id]


# -- exportación ---------------------------------------------------------------------------------------


def test_exported_script_adds_the_paths_and_lists_the_imported_packages(registry, tmp_path, libs):
    apply_import_paths([str(libs)])
    g, node = custom_graph(registry, tmp_path)
    src = tmp_path / "in.png"
    cv2.imencode(".png", np.full((6, 6), 100, np.uint8))[1].tofile(str(src))
    load = g.add_node("input.load_image", params={"path": str(src), "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    out = tmp_path / "o.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(node.id, "result", thr.id, "thresh")
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", save.id, "image")
    assert run(g).ok
    code = CodeGenerator(ExecutionPlan.from_graph(g), "t").generate()
    assert f"sys.path.append({str(libs)!r})" in code
    assert f"# Paquetes que importan los nodos personalizados: {MODULE}" in code
    assert code.index("sys.path.append") < code.index("def make_")  # antes del código del nodo
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr and out.exists()


def test_script_without_import_paths_or_extra_packages_stays_clean(registry, tmp_path):
    lib = CustomNodeLibrary(registry, tmp_path / "lib.json")
    spec = lib.create(
        "Doble", "X", "import math\n\n\ndef f(x: int) -> int:\n    return int(math.sqrt(x))\n"
    )
    g = Graph(registry)
    node = g.add_node(spec.id, input_values={"x": 9})
    thr = g.add_node("image.threshold")
    load = g.add_node("input.load_image", params={"path": "x.png"})
    save = g.add_node("output.save_image", params={"path": str(tmp_path / "o.png")})
    g.add_link(node.id, "result", thr.id, "thresh")
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", save.id, "image")
    code = CodeGenerator(ExecutionPlan.from_graph(g), "t").generate()
    assert "sys.path.append" not in code and "Paquetes que importan" not in code


# -- diálogo de rutas ------------------------------------------------------------------------------------


def test_paths_dialog_adds_removes_and_flags_missing_folders(qtbot, tmp_path, libs, monkeypatch):
    dialog = ImportPathsDialog([str(libs)])
    qtbot.addWidget(dialog)
    assert dialog.paths() == [str(libs)] and dialog.note.text() == ""
    assert dialog.add_path(str(tmp_path / "no_existe")) is True
    assert dialog.add_path(str(tmp_path / "no_existe")) is False  # repetida
    assert dialog.add_path("   ") is False
    assert (
        "No existe" in dialog.note.text()
        and dialog.listing.item(1).toolTip() == "Esta carpeta no existe"
    )
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path))
    )
    dialog.add_folder()
    assert dialog.paths()[-1] == str(tmp_path)
    dialog.listing.setCurrentRow(1)
    assert dialog.btn_remove.isEnabled()
    dialog.remove_selected()
    assert dialog.paths() == [str(libs), str(tmp_path)] and dialog.note.text() == ""
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    dialog.add_folder()  # cancelar no añade nada
    assert len(dialog.paths()) == 2


def test_custom_nodes_dialog_emits_new_paths_and_refreshes_the_warnings(
    qtbot, registry, tmp_path, libs, monkeypatch
):
    lib = CustomNodeLibrary(registry, tmp_path / "lib.json")
    dialog = CustomNodesDialog(lib, start_new=True, import_paths=[])
    qtbot.addWidget(dialog)
    dialog.code.setPlainText(USER_CODE)
    dialog.refresh_analysis()
    assert MODULE in dialog.info.toPlainText() and "no se encuentra" in dialog.info.toPlainText()
    received = []
    dialog.import_paths_changed.connect(received.append)

    def fake_exec(self):
        self.add_path(str(libs))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ImportPathsDialog, "exec", fake_exec)
    apply_import_paths([str(libs)])  # lo que haría la ventana al recibir la señal
    assert dialog.edit_import_paths() is True
    assert received == [[str(libs)]] and dialog.import_paths == [str(libs)]
    assert "no se encuentra" not in dialog.info.toPlainText()
    assert dialog.set_import_paths([str(libs)]) is False  # sin cambios: no emite de nuevo
    monkeypatch.setattr(ImportPathsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert dialog.edit_import_paths() is False and len(received) == 1
    dialog._dirty = False


# -- ventana principal -------------------------------------------------------------------------------------


def make_window(qtbot, registry):
    window = MainWindow(registry)
    window._confirm_discard = lambda: True
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def test_window_applies_and_saves_the_paths_and_restores_them_at_startup(
    qtbot, registry, libs, monkeypatch
):
    win = make_window(qtbot, registry)
    captured = {}
    monkeypatch.setattr(
        CustomNodesDialog,
        "exec",
        lambda self: captured.update(paths=self.import_paths, dialog=self) or 0,
    )
    win.open_custom_nodes()
    assert captured["paths"] == []
    captured["dialog"]._dirty = False
    win._on_import_paths_changed([str(libs)])
    assert str(libs) in sys.path and win.prefs.import_paths == [str(libs)]
    assert load_preferences(preferences_path())[0].import_paths == [str(libs)]

    apply_import_paths([])  # simula cerrar y volver a abrir la aplicación
    assert str(libs) not in sys.path
    again = make_window(qtbot, load_builtin_nodes().copy())
    assert str(libs) in sys.path and again.prefs.import_paths == [str(libs)]
    win.open_custom_nodes()
    assert captured["paths"] == [str(libs)]
    captured["dialog"]._dirty = False


def test_a_node_that_failed_on_import_runs_after_adding_the_folder_in_the_window(
    qtbot, registry, libs
):
    win = make_window(qtbot, registry)
    spec = win.custom_library.create("Usa mi módulo", "Mis nodos", USER_CODE)
    win.runner.auto_run = False
    node = win.graph.add_node(spec.id, input_values={"x": 4})
    win.runner.run(side_effects=False)
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=10000)
    assert node.id in win.last_result.errors
    win.last_result = None
    win._on_import_paths_changed([str(libs)])
    win.runner.run(side_effects=False)
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=10000)
    assert win.last_result.outputs[node.id]["result"] == 9
