"""Nodos de conversión (número/texto/entero) y String Viewer."""

import subprocess
import sys

import cv2
import numpy as np
import pytest

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.graph import Graph
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.library.convert import parse_number
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui.main_window import MainWindow

REGISTRY = load_builtin_nodes()


def run(graph):
    return Executor().run(ExecutionPlan.from_graph(graph), ExecContext())


def value_of(type_id, output, params=None, **inputs):
    g = Graph(REGISTRY)
    node = g.add_node(type_id, params=params or {}, input_values=inputs)
    result = run(g)
    assert result.ok, result.errors
    return result.outputs[node.id][output]


def test_conversion_nodes_share_one_category_with_the_color_ones():
    labels = {c.label for c in REGISTRY if c.category == "Conversión"}
    assert labels == {
        "Number to String",
        "String to Number",
        "Integer to Float",
        "Float to Integer",
        "RGB to HSV",
        "HSV to RGB",
        "Convert Color Space",
    }


@pytest.mark.parametrize(
    "value,decimals,expected",
    [
        (3.14159, 2, "3.14"),
        (3.14159, 0, "3"),
        (2.0, 3, "2.000"),
        (-0.5, 1, "-0.5"),
        (1e6, 1, "1000000.0"),
    ],
)
def test_number_to_string(value, decimals, expected):
    assert (
        value_of("convert.number_to_string", "text", {"decimals": decimals}, value=value)
        == expected
    )


@pytest.mark.parametrize(
    "text,expected",
    [("2.5", 2.5), ("2,5", 2.5), ("  -7 ", -7.0), ("1e3", 1000.0), ("0", 0.0)],
)
def test_string_to_number_accepts_comma_and_spaces(text, expected):
    assert value_of("convert.string_to_number", "value", text=text) == expected
    assert value_of("convert.string_to_number", "valid", text=text) is True


@pytest.mark.parametrize("text", ["", "abc", "1.2.3", "nan", "inf", "-inf"])
def test_invalid_text_uses_the_default_or_reports_an_error(text):
    params = {"default": 9.5}
    assert value_of("convert.string_to_number", "value", params, text=text) == 9.5
    assert value_of("convert.string_to_number", "valid", params, text=text) is False
    g = Graph(REGISTRY)
    node = g.add_node(
        "convert.string_to_number", params={"on_error": "error"}, input_values={"text": text}
    )
    assert "no es un número" in run(g).errors[node.id]


def test_parse_number_rejects_non_finite_values():
    for bad in ("nan", "inf", "x"):
        with pytest.raises(ValueError):
            parse_number(bad)


def test_integer_to_float():
    value = value_of("convert.integer_to_float", "value", value=7)
    assert value == 7.0 and isinstance(value, float)


@pytest.mark.parametrize(
    "mode,value,expected",
    [
        ("floor", 2.7, 2),
        ("floor", -2.1, -3),
        ("ceil", 2.1, 3),
        ("ceil", -2.7, -2),
        ("round", 2.6, 3),
        ("round", 2.4, 2),
        ("trunc", -2.9, -2),
        ("trunc", 2.9, 2),
    ],
)
def test_float_to_integer_modes(mode, value, expected):
    result = value_of("convert.float_to_integer", "value", {"mode": mode}, value=value)
    assert result == expected and isinstance(result, int)


def test_conversions_chain_through_links():
    g = Graph(REGISTRY)
    slider = g.add_node("input.slider", params={"minimum": 0, "maximum": 10, "value": 7.3})
    ceil = g.add_node("convert.float_to_integer", params={"mode": "ceil"})
    back = g.add_node("convert.integer_to_float")
    text = g.add_node("convert.number_to_string", params={"decimals": 1})
    parsed = g.add_node("convert.string_to_number")
    g.add_link(slider.id, "value", ceil.id, "value")
    g.add_link(ceil.id, "value", back.id, "value")
    g.add_link(back.id, "value", text.id, "value")
    g.add_link(text.id, "text", parsed.id, "text")
    result = run(g)
    assert result.outputs[text.id]["text"] == "8.0" and result.outputs[parsed.id]["value"] == 8.0


# -- exportación ------------------------------------------------------------------------------------


@pytest.fixture
def image_path(tmp_path):
    img = np.random.default_rng(2).integers(0, 255, (12, 16), dtype=np.uint8)
    path = tmp_path / "in.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


def read_png(path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)


def test_exported_script_matches_the_engine_for_every_conversion(tmp_path, image_path):
    g = Graph(REGISTRY)
    slider = g.add_node("input.slider", params={"minimum": 0, "maximum": 255, "value": 99.7})
    ceil = g.add_node("convert.float_to_integer", params={"mode": "ceil"})
    floor = g.add_node("convert.float_to_integer", params={"mode": "floor"})
    text = g.add_node("convert.number_to_string", params={"decimals": 3})
    parsed = g.add_node("convert.string_to_number", params={"on_error": "default"})
    bad = g.add_node(
        "convert.string_to_number", params={"default": 5.0}, input_values={"text": "x"}
    )
    total = g.add_node("math.add")
    asfloat = g.add_node("convert.integer_to_float")
    g.add_link(slider.id, "value", ceil.id, "value")
    g.add_link(slider.id, "value", floor.id, "value")
    g.add_link(slider.id, "value", text.id, "value")
    g.add_link(text.id, "text", parsed.id, "text")
    g.add_link(ceil.id, "value", asfloat.id, "value")
    g.add_link(asfloat.id, "value", total.id, "a")
    g.add_link(parsed.id, "value", total.id, "b")
    thr_sources = g.add_node("math.add")
    g.add_link(total.id, "result", thr_sources.id, "a")
    g.add_link(bad.id, "value", thr_sources.id, "b")
    g.add_link(floor.id, "value", g.add_node("math.add").id, "a")
    load = g.add_node("input.load_image", params={"path": image_path, "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    out = tmp_path / "o.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(thr_sources.id, "result", thr.id, "thresh")
    g.add_link(thr.id, "image", save.id, "image")
    expected = Executor().run(ExecutionPlan.from_graph(g), ExecContext(side_effects=True))
    assert expected.ok, expected.errors
    engine = read_png(out)
    out.unlink()
    code = CodeGenerator(ExecutionPlan.from_graph(g), "t").generate()
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert np.array_equal(read_png(out), engine) and "import math" in code


def test_exported_string_to_number_raises_when_configured_to(tmp_path, image_path):
    g = Graph(REGISTRY)
    node = g.add_node(
        "convert.string_to_number", params={"on_error": "error"}, input_values={"text": "zzz"}
    )
    load = g.add_node("input.load_image", params={"path": image_path, "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    save = g.add_node("output.save_image", params={"path": str(tmp_path / "o.png")})
    g.add_link(node.id, "value", thr.id, "thresh")
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", save.id, "image")
    script = tmp_path / "s.py"
    script.write_text(CodeGenerator(ExecutionPlan.from_graph(g), "t").generate(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True
    )
    assert proc.returncode != 0 and "zzz" in proc.stderr


# -- String Viewer ---------------------------------------------------------------------------------


def test_string_viewer_declaration_and_run():
    cls = REGISTRY.require("output.string_viewer")
    assert cls.shows_text == "text" and cls.category == "Salidas" and not cls.outputs
    g = Graph(REGISTRY)
    num = g.add_node("convert.number_to_string", input_values={"value": 1.5})
    viewer = g.add_node("output.string_viewer")
    g.add_link(num.id, "text", viewer.id, "text")
    result = run(g)
    assert result.ok and result.inputs[viewer.id]["text"] == "1.50"


def test_string_viewer_without_connection_reports_the_missing_input():
    g = Graph(REGISTRY)
    viewer = g.add_node("output.string_viewer")
    assert "Falta conectar" in run(g).errors[viewer.id]


def test_exported_string_viewer_prints_only_when_the_text_changes(tmp_path, image_path):
    g = Graph(REGISTRY)
    tick = g.add_node("input.tick", params={"interval": 0.02})
    text = g.add_node("convert.number_to_string", params={"decimals": 0})
    viewer = g.add_node("output.string_viewer")
    load = g.add_node("input.load_image", params={"path": image_path})
    show = g.add_node("output.image_viewer")
    g.add_link(tick.id, "count", text.id, "value")
    g.add_link(text.id, "text", viewer.id, "text")
    g.add_link(load.id, "image", show.id, "image")
    script = tmp_path / "s.py"
    script.write_text(CodeGenerator(ExecutionPlan.from_graph(g), "t").generate(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show", "--max-frames", "30"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.split()
    assert lines[0] == "1" and len(lines) == len(set(lines))  # sin repetidos seguidos


# -- en la ventana ----------------------------------------------------------------------------------


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes().copy())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def run_in_window(win, qtbot):
    win.last_result = None
    win.runner.run(side_effects=False)
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=10000)


def test_string_viewer_shows_its_text_inside_the_node_and_in_the_viewer(win, qtbot):
    ctl = win.controller
    num = ctl.add_node("convert.number_to_string", (0, 0))
    ctl.set_input_value(num, "value", 2.5)
    viewer = ctl.add_node("output.string_viewer", (300, 0))
    win.graph.add_link(num, "text", viewer, "text")
    item = win.scene.node_items[viewer]
    assert item.pinnable and item.text is None
    height = item.height
    run_in_window(win, qtbot)
    assert item.text == "2.50" and item.height > height and item.text_rect() is not None
    win.scene.select_nodes([viewer])
    assert win.viewer.message.text() == "2.50" and win.viewer.source.text() == "String Viewer"
    assert not win.view.grab().isNull()
    ctl.set_input_value(num, "value", 7.25)
    run_in_window(win, qtbot)
    assert item.text == "7.25"


def test_long_text_is_cut_to_fit_the_node_but_complete_in_the_viewer(win, qtbot):
    ctl = win.controller
    num = ctl.add_node("convert.number_to_string", (0, 0))
    ctl.set_input_value(num, "value", 1.0)
    viewer = ctl.add_node("output.string_viewer", (300, 0))
    win.graph.add_link(num, "text", viewer, "text")
    item = win.scene.node_items[viewer]
    long_text = "palabra " * 400
    item.set_text(long_text)
    assert item.text == long_text and item._text_shown.endswith("…")
    assert len(item._text_shown) < len(long_text) and item._text_extra <= 130
    assert item.toolTip().startswith("palabra")
    item.set_text("")
    assert item._text_shown == "" and item._text_extra > 0
    item.set_text(None)
    assert item.text_rect() is None and item.height == item._base_height


def test_text_is_removed_when_the_input_fails_or_is_disconnected(win, qtbot):
    ctl = win.controller
    text = ctl.add_node("convert.string_to_number", (0, 0))
    viewer = ctl.add_node("output.string_viewer", (300, 0))
    win.scene.node_items[viewer].set_text("viejo")
    run_in_window(win, qtbot)  # el visor no tiene conexión: error
    assert win.scene.node_items[viewer].text is None
    assert text


def test_preview_and_text_stack_without_overlapping(win):
    ctl = win.controller
    viewer = ctl.add_node("output.string_viewer", (0, 0))
    item = win.scene.node_items[viewer]
    base = item.height
    item.set_text("hola")
    with_text = item.height
    item.set_preview(np.zeros((40, 60, 3), np.uint8))
    assert item.height > with_text > base
    preview, text = item.preview_rect(), item.text_rect()
    assert preview.bottom() <= text.top() + 1 or text.bottom() <= preview.top() + 1
    item.set_preview(None)
    assert item.height == with_text
