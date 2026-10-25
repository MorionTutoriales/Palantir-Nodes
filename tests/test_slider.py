"""Nodo Slider: rango y modo entero elegidos en las propiedades, deslizador dentro del nodo."""

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.graph import Graph
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.nodes.specs import resolve_slider
from palantir_nodes.persistence import ProjectData, dump, load
from palantir_nodes.ui.main_window import MainWindow

# -- lógica pura ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args,expected",
    [
        ((0, 10, 5, False), (0.0, 10.0, 5.0)),
        ((0, 10, 50, False), (0.0, 10.0, 10.0)),  # se recorta al máximo
        ((0, 10, -3, False), (0.0, 10.0, 0.0)),
        ((10, 0, 4, False), (0.0, 10.0, 4.0)),  # extremos al revés
        ((0, 10, 4.6, True), (0.0, 10.0, 5.0)),  # modo entero redondea
        ((0.2, 3.8, 0.0, True), (1.0, 3.0, 1.0)),  # el rango se reduce a los enteros que contiene
        ((0.2, 0.8, 0.5, True), (1.0, 1.0, 1.0)),  # sin enteros dentro: el siguiente entero
        ((5, 5, 9, False), (5.0, 5.0, 5.0)),
        ((-10, -2, 0, False), (-10.0, -2.0, -2.0)),
    ],
)
def test_resolve_slider(args, expected):
    assert resolve_slider(*args) == expected


# -- motor y exportación --------------------------------------------------------------------


def slider_value(**params):
    g = Graph(load_builtin_nodes())
    node = g.add_node("input.slider", params=params)
    result = Executor().run(ExecutionPlan.from_graph(g), ExecContext())
    assert result.ok
    return result.outputs[node.id]["value"], g, node


def test_defaults_and_declared_parameters():
    cls = load_builtin_nodes().require("input.slider")
    assert [p.name for p in cls.params] == ["value", "minimum", "maximum", "integer"]
    assert cls.params[0].range_params == ("minimum", "maximum", "integer")
    assert [o.type.value for o in cls.outputs] == ["Float"]
    assert not cls.inputs and not cls.socket_inputs()  # ninguna entrada: es una fuente de valor
    assert slider_value()[0] == 0.5


def test_value_follows_range_and_integer_mode():
    assert slider_value(minimum=0.0, maximum=100.0, value=37.5)[0] == 37.5
    assert slider_value(minimum=0.0, maximum=100.0, value=37.5, integer=True)[0] == 38.0
    assert slider_value(minimum=10.0, maximum=20.0, value=3.0)[0] == 10.0  # se sube el mínimo
    assert slider_value(minimum=0.0, maximum=1.0, value=7.0)[0] == 1.0  # al reducir el máximo


def test_output_feeds_integer_and_float_parameters():
    g = Graph(load_builtin_nodes())
    slider = g.add_node(
        "input.slider", params={"minimum": 1, "maximum": 31, "integer": True, "value": 9}
    )
    blur = g.add_node("image.gaussian_blur")
    g.add_link(slider.id, "value", blur.id, "sigma")  # Float -> Float
    assert (
        Executor().run(ExecutionPlan.from_graph(g), ExecContext()).outputs[slider.id]["value"]
        == 9.0
    )


def test_exported_script_uses_the_same_value(tmp_path):
    g = Graph(load_builtin_nodes())
    slider = g.add_node(
        "input.slider", params={"minimum": 0, "maximum": 10, "integer": True, "value": 6.6}
    )
    src = tmp_path / "in.png"
    cv2.imencode(".png", np.full((4, 4), 100, np.uint8))[1].tofile(str(src))
    load_node = g.add_node("input.load_image", params={"path": str(src), "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    g.add_link(slider.id, "value", thr.id, "thresh")
    g.add_link(load_node.id, "image", thr.id, "image")
    save = g.add_node("output.save_image", params={"path": str(tmp_path / "o.png")})
    g.add_link(thr.id, "image", save.id, "image")
    code = CodeGenerator(ExecutionPlan.from_graph(g), "t").generate()
    assert "= 7.0" in code
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "o.png").exists()


def test_project_roundtrip_keeps_all_four_settings():
    registry = load_builtin_nodes()
    g = Graph(registry)
    g.add_node("input.slider", params={"minimum": -5, "maximum": 5, "integer": True, "value": 2})
    graph, _ = load(dump(g, ProjectData(), "t"), registry)
    node = next(iter(graph.nodes.values()))
    assert node.params == {"minimum": -5.0, "maximum": 5.0, "integer": True, "value": 2.0}


# -- dentro del nodo, con el ratón ------------------------------------------------------------


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def send(win, kind, scene_pos, button, buttons):
    view = win.view
    local = QPointF(view.mapFromScene(scene_pos))
    glob = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    QApplication.sendEvent(
        view.viewport(),
        QMouseEvent(kind, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier),
    )


def field_point(win, node_id, fraction):
    rect = win.scene.node_items[node_id].field_scene_rect("value", "param")
    return QPointF(rect.left() + rect.width() * fraction, rect.center().y())


def test_clicking_and_dragging_the_slider_sets_the_value(win):
    ctl = win.controller
    node_id = ctl.add_node("input.slider", (0, 0))
    ctl.set_param(node_id, "maximum", 100.0)
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    send(win, QEvent.Type.MouseButtonPress, field_point(win, node_id, 0.25), left, left)
    assert win.graph.node(node_id).params["value"] == pytest.approx(25.0, abs=2.0)
    send(win, QEvent.Type.MouseMove, field_point(win, node_id, 0.8), none, left)
    send(win, QEvent.Type.MouseButtonRelease, field_point(win, node_id, 0.8), left, none)
    assert win.graph.node(node_id).params["value"] == pytest.approx(80.0, abs=2.0)
    win.undo_stack.undo()
    assert win.graph.node(node_id).params["value"] != pytest.approx(80.0, abs=2.0)


def test_dragging_past_the_ends_clamps_and_integer_mode_snaps(win):
    ctl = win.controller
    node_id = ctl.add_node("input.slider", (0, 0))
    ctl.set_param(node_id, "maximum", 10.0)
    ctl.set_param(node_id, "integer", True)
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    send(win, QEvent.Type.MouseButtonPress, field_point(win, node_id, 0.5), left, left)
    assert win.graph.node(node_id).params["value"] == 5.0
    send(win, QEvent.Type.MouseMove, field_point(win, node_id, 3.0), none, left)
    assert win.graph.node(node_id).params["value"] == 10.0
    send(win, QEvent.Type.MouseMove, field_point(win, node_id, -2.0), none, left)
    send(win, QEvent.Type.MouseButtonRelease, field_point(win, node_id, -2.0), left, none)
    assert win.graph.node(node_id).params["value"] == 0.0


def test_slider_does_not_move_the_node_and_double_click_opens_the_text_editor(win):
    ctl = win.controller
    node_id = ctl.add_node("input.slider", (0, 0))
    item = win.scene.node_items[node_id]
    start = item.pos()
    requests = []
    win.scene.field_edit_requested.connect(lambda *args: requests.append(args[:3]))
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    point = field_point(win, node_id, 0.5)
    send(win, QEvent.Type.MouseButtonPress, point, left, left)
    send(win, QEvent.Type.MouseButtonRelease, point, left, none)
    send(win, QEvent.Type.MouseButtonDblClick, point, left, left)
    send(win, QEvent.Type.MouseButtonRelease, point, left, none)
    assert item.pos() == start
    assert requests == [(node_id, "param", "value")]
    win.view.field_editor.close_inline(commit=False)


def test_range_changes_rescale_the_displayed_slider(win):
    ctl = win.controller
    node_id = ctl.add_node("input.slider", (0, 0))
    item = win.scene.node_items[node_id]
    ctl.set_param(node_id, "value", 0.5)
    row = next(r for r in item._rows if r.name == "value" and r.kind == "param")
    assert item._slider_state(row) == (0.0, 1.0, 0.5, False)
    ctl.set_param(node_id, "maximum", 0.25)  # el valor guardado queda fuera: se muestra recortado
    assert item._slider_state(row) == (0.0, 0.25, 0.25, False)
    ctl.set_param(node_id, "integer", True)
    assert item._slider_state(row)[3] is True
    pixmap = win.view.grab()  # el pintado no falla con ningún estado
    assert not pixmap.isNull()
