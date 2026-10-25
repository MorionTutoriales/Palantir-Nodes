"""Compilar el grafo a un ejecutable: órdenes de PyInstaller, diálogo y menú."""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from palantir_nodes.build import compiler
from palantir_nodes.customnodes.paths import apply_import_paths
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui import compile_dialog
from palantir_nodes.ui.compile_dialog import CompileDialog
from palantir_nodes.ui.main_window import MainWindow

# -- órdenes ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mi grafo", "mi_grafo"),
        ("  Ñandú*2!  ", "and_2"),
        ("a/b\\c", "a_b_c"),
        ("ok-1_2", "ok-1_2"),
        ("", "grafo"),
        ("***", "grafo"),
    ],
)
def test_safe_name(raw, expected):
    assert compiler.safe_name(raw) == expected


def test_executable_path_for_one_file_and_for_a_folder(tmp_path):
    suffix = ".exe" if sys.platform == "win32" else ""
    assert compiler.executable_path(tmp_path, "mi grafo") == tmp_path / f"mi_grafo{suffix}"
    assert compiler.executable_path(tmp_path, "g", onefile=False) == tmp_path / "g" / f"g{suffix}"


def test_only_scripts_that_import_mediapipe_collect_it():
    plain = "import cv2\n# import mediapipe\nprint('mediapipe')\n"
    assert compiler.packages_to_collect(plain) == []
    inside_a_function = "def f():\n    from mediapipe.tasks import python as tasks\n"
    assert compiler.packages_to_collect(inside_a_function) == ["mediapipe"]
    assert compiler.packages_to_collect("import mediapipe as mp\n") == ["mediapipe"]
    header = '"""requiere: pip install opencv-python numpy mediapipe"""\nimport cv2\n'
    assert compiler.packages_to_collect(header) == []  # el encabezado no cuenta


def test_pyinstaller_command_options(tmp_path):
    program, args = compiler.pyinstaller_command(
        tmp_path / "g.py",
        "mi grafo",
        tmp_path / "salida",
        tmp_path / "tmp",
        onefile=False,
        console=False,
        search_paths=["C:/libs", "D:/otras"],
        collect=["mediapipe"],
    )
    assert program == sys.executable and args[:2] == ["-m", "PyInstaller"]
    assert "--onedir" in args and "--onefile" not in args and "--noconsole" in args
    assert args[args.index("--name") + 1] == "mi_grafo"
    assert args[args.index("--distpath") + 1] == str(tmp_path / "salida")
    assert args[args.index("--workpath") + 1] == str(
        tmp_path / "tmp" / "work"
    )  # nada junto a la salida
    assert args[args.index("--specpath") + 1] == str(tmp_path / "tmp" / "spec")
    paths = [args[i + 1] for i, a in enumerate(args) if a == "--paths"]
    assert paths == ["C:/libs", "D:/otras"] and args[args.index("--collect-all") + 1] == "mediapipe"
    assert args[-1] == str(tmp_path / "g.py")
    default = compiler.pyinstaller_command("g.py", "g", "o", "t")[1]
    assert "--onefile" in default and "--console" in default and "--collect-all" not in default


def test_pyinstaller_availability_follows_find_spec(monkeypatch):
    monkeypatch.setattr(compiler.importlib.util, "find_spec", lambda name: object())
    assert compiler.pyinstaller_available() is True
    monkeypatch.setattr(compiler.importlib.util, "find_spec", lambda name: None)
    assert compiler.pyinstaller_available() is False

    def broken(name):
        raise ValueError("raro")

    monkeypatch.setattr(compiler.importlib.util, "find_spec", broken)
    assert compiler.pyinstaller_available() is False


# -- diálogo --------------------------------------------------------------------------------------------

CODE = "import cv2\nprint('hola')\n"


@pytest.fixture
def fake_build(monkeypatch, tmp_path):
    """Un «PyInstaller» falso: un script que crea el ejecutable donde tocaría y se despide."""
    state = {"code": 0, "scripts": [], "existed": []}
    monkeypatch.setattr(compiler, "pyinstaller_available", lambda: True)

    def fake_command(script, name, dist, work, **options):
        state["scripts"].append(Path(script))
        state["existed"].append(Path(script).exists())
        state["options"] = options
        body = (
            f"import sys, pathlib; print('compilando', {str(name)!r}); "
            f"p = pathlib.Path({str(compiler.executable_path(dist, name, options.get('onefile', True)))!r}); "
            f"p.parent.mkdir(parents=True, exist_ok=True); p.write_text('exe') if {state['code']} == 0 else None; "
            f"sys.exit({state['code']})"
        )
        return sys.executable, ["-c", body]

    monkeypatch.setattr(compiler, "pyinstaller_command", fake_command)
    return state


def make_dialog(qtbot, tmp_path, **kwargs):
    dialog = CompileDialog(CODE, name="Mi grafo", folder=str(tmp_path / "salida"), **kwargs)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def wait_done(qtbot, dialog):
    qtbot.waitUntil(lambda: not dialog.running, timeout=20000)


def test_successful_build_writes_the_script_runs_it_and_cleans_up(qtbot, tmp_path, fake_build):
    dialog = make_dialog(qtbot, tmp_path, search_paths=["C:/libs"])
    assert (
        dialog.name_edit.text() == "Mi_grafo"
        and dialog.status.text() == "PyInstaller está instalado."
    )
    assert dialog.compile() is True
    assert not dialog.btn_compile.isEnabled() and not dialog.btn_close.isEnabled()  # ocupado
    dialog.reject()  # a mitad de la compilación no se cierra
    assert dialog.isVisible()
    wait_done(qtbot, dialog)
    script = fake_build["scripts"][0]
    assert script.name == "Mi_grafo.py" and fake_build["existed"] == [True]  # existía al compilar
    assert not script.exists() and not script.parent.exists()  # la carpeta temporal se borró
    assert fake_build["options"]["search_paths"] == ["C:/libs"] and fake_build["options"]["onefile"]
    text = dialog.log.toPlainText()
    assert "compilando Mi_grafo" in text and "Listo:" in text
    assert dialog.result_path == compiler.executable_path(tmp_path / "salida", "Mi_grafo")
    assert dialog.result_path.exists() and dialog.btn_open.isEnabled()
    assert dialog.btn_compile.isEnabled() and dialog.btn_close.isEnabled()


def test_options_reach_the_command(qtbot, tmp_path, fake_build):
    dialog = make_dialog(qtbot, tmp_path)
    dialog.onefile.setChecked(False)
    dialog.console.setChecked(False)
    dialog.name_edit.setText("otro nombre!")
    dialog.compile()
    wait_done(qtbot, dialog)
    assert fake_build["options"]["onefile"] is False and fake_build["options"]["console"] is False
    assert dialog.name_edit.text() == "otro_nombre"
    assert dialog.result_path == tmp_path / "salida" / "otro_nombre" / dialog.result_path.name


def test_failed_build_reports_the_code_and_leaves_no_result(qtbot, tmp_path, fake_build):
    fake_build["code"] = 4
    dialog = make_dialog(qtbot, tmp_path)
    dialog.compile()
    wait_done(qtbot, dialog)
    assert "no terminó bien (código 4)" in dialog.log.toPlainText()
    assert dialog.result_path is None and not dialog.btn_open.isEnabled()
    assert "falló" in dialog.status.text() and dialog.btn_compile.isEnabled()
    assert not fake_build["scripts"][0].parent.exists()


def test_missing_pyinstaller_is_installed_first_after_asking(
    qtbot, tmp_path, fake_build, monkeypatch
):
    marker = tmp_path / "pyinstaller_instalado"
    monkeypatch.setattr(compiler, "pyinstaller_available", lambda: marker.exists())
    steps = []

    def fake_pip(packages, no_deps=False):
        steps.append(list(packages))
        return sys.executable, [
            "-c",
            f"import pathlib; print('pip', {packages!r}); pathlib.Path({str(marker)!r}).write_text('x')",
        ]

    monkeypatch.setattr(compile_dialog, "pip_command", fake_pip)
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(
            lambda p, t, text, *a, **k: asked.append(text) or QMessageBox.StandardButton.No
        ),
    )
    dialog = make_dialog(qtbot, tmp_path)
    assert "Falta PyInstaller" in dialog.status.text()
    assert (
        dialog.compile() is False and not steps and "pip install pyinstaller" in asked[0]
    )  # dijo que no

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    assert dialog.compile() is True
    wait_done(qtbot, dialog)
    text = dialog.log.toPlainText()
    assert steps == [["pyinstaller"]] and text.index("pip ['pyinstaller']") < text.index(
        "compilando"
    )
    assert dialog.result_path.exists() and dialog.status.text() == "Compilación terminada."


def test_failed_install_stops_before_building(qtbot, tmp_path, fake_build, monkeypatch):
    monkeypatch.setattr(compiler, "pyinstaller_available", lambda: False)
    monkeypatch.setattr(
        compile_dialog,
        "pip_command",
        lambda packages, no_deps=False: (sys.executable, ["-c", "import sys; sys.exit(7)"]),
    )
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    dialog = make_dialog(qtbot, tmp_path)
    dialog.compile()
    wait_done(qtbot, dialog)
    text = dialog.log.toPlainText()
    assert "código 7" in text and "compilando" not in text  # no llegó a compilar
    assert not fake_build["scripts"][0].parent.exists()  # y la carpeta temporal se borró


def test_unwritable_output_folder_is_reported(qtbot, tmp_path, fake_build, monkeypatch):
    blocker = tmp_path / "archivo"
    blocker.write_text("x")
    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda p, t, text, *a, **k: shown.append(text))
    )
    dialog = CompileDialog(CODE, folder=str(blocker / "dentro"))
    qtbot.addWidget(dialog)
    assert (
        dialog.compile() is False and "carpeta de salida" in shown[0] and not fake_build["scripts"]
    )


def test_start_failure_and_packaged_app(qtbot, tmp_path, fake_build, monkeypatch):
    monkeypatch.setattr(
        compiler, "pyinstaller_command", lambda *a, **k: (str(tmp_path / "no_existe.exe"), [])
    )
    dialog = make_dialog(qtbot, tmp_path)
    dialog.compile()
    wait_done(qtbot, dialog)
    assert (
        "No se pudo ejecutar Python" in dialog.log.toPlainText() and dialog.btn_compile.isEnabled()
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    packaged = make_dialog(qtbot, tmp_path)
    assert not packaged.btn_compile.isEnabled() and packaged.compile() is False


# -- menú -----------------------------------------------------------------------------------------------


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes().copy())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def valid_graph(win, tmp_path):
    load = win.controller.add_node("input.load_image", (0, 0))
    win.controller.set_param(load, "path", str(tmp_path / "x.png"))
    viewer = win.controller.add_node("output.image_viewer", (300, 0))
    win.graph.add_link(load, "image", viewer, "image")


def test_menu_action_opens_the_dialog_with_the_exported_script(win, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        CompileDialog,
        "exec",
        lambda self: (
            seen.update(
                code=self._code,
                name=self.name_edit.text(),
                folder=self.folder_edit.text(),
                paths=self._search_paths,
            )
            or 0
        ),
    )
    assert win.action_compile.shortcut().toString() == "Ctrl+Shift+E"
    assert "Compilar a ejecutable…" in [
        a.text()
        for m in win.menuBar().findChildren(type(win.menuBar().addMenu("x")))
        for a in m.actions()
    ]
    valid_graph(win, tmp_path)
    apply_import_paths([str(tmp_path)])
    try:
        win.action_compile.trigger()
    finally:
        apply_import_paths([])
    assert "cv2.imshow" in seen["code"] and seen["paths"] == [str(tmp_path)]
    assert seen["name"] == win.project_name.replace(" ", "_") or seen["name"]
    assert seen["folder"].endswith("Palantir Nodes")  # sin proyecto guardado: carpeta por defecto
    win.project_path = tmp_path / "proyecto.json"
    win.action_compile.trigger()
    assert seen["folder"] == str(tmp_path / "ejecutables")


def test_graph_that_cannot_be_exported_warns_instead_of_opening_the_dialog(win, monkeypatch):
    opened, shown = [], []
    monkeypatch.setattr(CompileDialog, "exec", lambda self: opened.append(1) or 0)
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda p, t, text, *a, **k: shown.append(text))
    )
    win.action_compile.trigger()  # grafo vacío: no hay nodos de salida
    assert not opened and "No se puede exportar" in shown[0]
