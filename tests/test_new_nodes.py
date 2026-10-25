"""Seno/coseno, conversión de color y el nodo Tick."""

import math
import random
import subprocess
import sys

import cv2
import numpy as np
import pytest

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.graph import Graph
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.engine.realtime import RealtimeSession
from palantir_nodes.media import timing
from palantir_nodes.media.timing import TickClock
from palantir_nodes.nodes.library._cv import hsv_to_rgb, rgb_to_hsv
from palantir_nodes.nodes.registry import load_builtin_nodes

REGISTRY = load_builtin_nodes()


def run(graph, **ctx):
    return Executor().run(ExecutionPlan.from_graph(graph), ExecContext(**ctx))


def run_script(tmp_path, graph, *extra):
    code = CodeGenerator(ExecutionPlan.from_graph(graph), "t").generate()
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show", *extra],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return code, proc


def read_png(path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)


@pytest.fixture
def image_path(tmp_path):
    img = np.random.default_rng(3).integers(0, 255, (24, 32, 3), dtype=np.uint8)
    path = tmp_path / "in.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


# -- seno y coseno ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "type_id,unit,angle,expected",
    [
        ("math.sin", "radians", math.pi / 2, 1.0),
        ("math.cos", "radians", 0.0, 1.0),
        ("math.sin", "degrees", 30.0, 0.5),
        ("math.cos", "degrees", 180.0, -1.0),
        ("math.sin", "degrees", -90.0, -1.0),
        ("math.cos", "radians", math.pi, -1.0),
    ],
)
def test_sine_and_cosine_values(type_id, unit, angle, expected):
    g = Graph(REGISTRY)
    node = g.add_node(type_id, params={"unit": unit}, input_values={"angle": angle})
    assert run(g).outputs[node.id]["result"] == pytest.approx(expected)


def test_sine_of_a_connected_value_and_its_range():
    g = Graph(REGISTRY)
    slider = g.add_node("input.slider", params={"minimum": 0, "maximum": 360, "value": 90})
    sin = g.add_node("math.sin", params={"unit": "degrees"})
    g.add_link(slider.id, "value", sin.id, "angle")
    assert run(g).outputs[sin.id]["result"] == pytest.approx(1.0)


def test_exported_script_matches_the_engine_for_trigonometry(tmp_path, image_path):
    g = Graph(REGISTRY)
    sin = g.add_node("math.sin", params={"unit": "degrees"}, input_values={"angle": 30.0})
    cos = g.add_node("math.cos", input_values={"angle": 1.0})
    add = g.add_node("math.add")
    g.add_link(sin.id, "result", add.id, "a")
    g.add_link(cos.id, "result", add.id, "b")
    load = g.add_node("input.load_image", params={"path": image_path, "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(add.id, "result", thr.id, "thresh")
    out = tmp_path / "o.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(thr.id, "image", save.id, "image")
    assert run(g, side_effects=True).ok
    engine = read_png(out)
    out.unlink()
    code, proc = run_script(tmp_path, g)
    assert proc.returncode == 0, proc.stderr
    assert "import math" in code and np.array_equal(read_png(out), engine)


# -- conversión de color --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rgb,hsv",
    [
        ((255, 0, 0), (0.0, 255.0, 255.0)),
        ((0, 255, 0), (60.0, 255.0, 255.0)),
        ((0, 0, 255), (120.0, 255.0, 255.0)),
        ((255, 255, 255), (0.0, 0.0, 255.0)),
        ((0, 0, 0), (0.0, 0.0, 0.0)),
    ],
)
def test_rgb_to_hsv_known_colors(rgb, hsv):
    assert rgb_to_hsv(rgb) == hsv
    g = Graph(REGISTRY)
    node = g.add_node("color.rgb_to_hsv", input_values={"color": rgb})
    assert run(g).outputs[node.id]["hsv"] == hsv


def test_hsv_to_rgb_known_values_and_clipping():
    assert hsv_to_rgb((60, 255, 255)) == (0, 255, 0)
    assert hsv_to_rgb((0, 0, 128)) == (128, 128, 128)
    assert hsv_to_rgb((500, 900, -3)) == (0, 0, 0)  # se recorta a H<=179, S<=255, V>=0
    assert hsv_to_rgb((59.6, 255, 255)) == hsv_to_rgb((60, 255, 255))  # redondea


def test_color_roundtrip_is_close_for_random_colors():
    rng = random.Random(7)
    for _ in range(500):
        color = tuple(rng.randrange(256) for _ in range(3))
        back = hsv_to_rgb(rgb_to_hsv(color))
        assert max(abs(a - b) for a, b in zip(color, back, strict=True)) <= 6


def test_color_nodes_chain_with_a_color_range_node(image_path):
    """El flujo típico: elegir un color, sacar su HSV y usarlo como rango del InRange."""
    g = Graph(REGISTRY)
    color = g.add_node("input.color", params={"color": (0, 0, 255)})
    to_hsv = g.add_node("color.rgb_to_hsv")
    back = g.add_node("color.hsv_to_rgb")
    g.add_link(color.id, "color", to_hsv.id, "color")
    g.add_link(to_hsv.id, "hsv", back.id, "hsv")
    result = run(g)
    assert result.ok and result.outputs[back.id]["color"] == (0, 0, 255)


@pytest.mark.parametrize("space", ["rgb", "hsv", "hls", "lab", "ycrcb"])
def test_convert_color_roundtrips_through_bgr(space):
    img = np.random.default_rng(1).integers(0, 255, (16, 20, 3), dtype=np.uint8)
    cls = REGISTRY.require("image.convert_color")
    there = cls().process(ExecContext(), {"image": img}, {"source": "bgr", "target": space})
    back = cls().process(ExecContext(), there, {"source": space, "target": "bgr"})["image"]
    assert back.shape == img.shape
    # Con 8 bits el ida y vuelta no es exacto (sobre todo en HSV/HLS), pero queda muy cerca.
    assert np.abs(back.astype(int) - img.astype(int)).mean() < 12


def test_convert_color_matches_opencv_and_handles_gray():
    img = np.random.default_rng(2).integers(0, 255, (10, 12, 3), dtype=np.uint8)
    cls = REGISTRY.require("image.convert_color")

    def convert(image, source, target):
        return cls().process(ExecContext(), {"image": image}, {"source": source, "target": target})[
            "image"
        ]

    assert np.array_equal(convert(img, "bgr", "rgb"), img[:, :, ::-1])
    assert np.array_equal(convert(img, "bgr", "gray"), cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    assert np.array_equal(convert(img, "bgr", "hsv"), cv2.cvtColor(img, cv2.COLOR_BGR2HSV))
    assert np.array_equal(convert(img, "bgr", "bgr"), img)
    gray = convert(img, "bgr", "gray")
    assert convert(gray, "gray", "bgr").shape == img.shape  # gris -> BGR
    assert convert(img, "gray", "rgb").shape == img.shape  # un origen gris acepta color
    with pytest.raises(ValueError, match="necesita una imagen de 3 canales"):
        convert(gray, "hsv", "bgr")


@pytest.mark.parametrize(
    "source,target",
    [("bgr", "hsv"), ("rgb", "lab"), ("hls", "gray"), ("gray", "bgr"), ("hsv", "rgb")],
)
def test_exported_script_matches_the_engine_for_convert_color(tmp_path, image_path, source, target):
    g = Graph(REGISTRY)
    load = g.add_node("input.load_image", params={"path": image_path})
    conv = g.add_node("image.convert_color", params={"source": source, "target": target})
    out = tmp_path / "o.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(load.id, "image", conv.id, "image")
    g.add_link(conv.id, "image", save.id, "image")
    assert run(g, side_effects=True).ok
    engine = read_png(out)
    out.unlink()
    _, proc = run_script(tmp_path, g)
    assert proc.returncode == 0, proc.stderr
    assert np.array_equal(read_png(out), engine)


def test_exported_script_matches_the_engine_for_color_values(tmp_path, image_path):
    g = Graph(REGISTRY)
    color = g.add_node("input.color", params={"color": (200, 40, 90)})
    to_hsv = g.add_node("color.rgb_to_hsv")
    back = g.add_node("color.hsv_to_rgb")
    g.add_link(color.id, "color", to_hsv.id, "color")
    g.add_link(to_hsv.id, "hsv", back.id, "hsv")
    load = g.add_node("input.load_image", params={"path": image_path})
    rng = g.add_node("image.in_range", params={"use_hsv": True})
    g.add_link(load.id, "image", rng.id, "image")
    out = tmp_path / "o.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(rng.id, "mask", save.id, "image")
    # el HSV calculado alimenta el límite inferior del rango (Vector3 -> Vector3)
    g.add_link(to_hsv.id, "hsv", rng.id, "lower")
    assert run(g, side_effects=True).ok
    engine = read_png(out)
    out.unlink()
    _, proc = run_script(tmp_path, g)
    assert proc.returncode == 0, proc.stderr
    assert np.array_equal(read_png(out), engine)


# -- Tick ---------------------------------------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(timing.time, "perf_counter", fake)
    return fake


def test_tick_fires_at_start_and_then_every_interval(clock):
    tick = TickClock(1.0)
    assert tick.read() == (True, 1, 0.0)  # al iniciar
    clock.now += 0.4
    assert tick.read()[0] is False
    clock.now += 0.6
    fired, count, seconds = tick.read()
    assert (fired, count) == (True, 2) and seconds == pytest.approx(1.0)
    assert tick.read()[0] is False  # un solo aviso por intervalo


def test_tick_without_firing_at_start(clock):
    tick = TickClock(2.0, at_start=False)
    assert tick.read()[:2] == (False, 0)
    clock.now += 2.0
    assert tick.read()[:2] == (True, 1)


def test_tick_does_not_fire_a_burst_after_a_stall(clock):
    tick = TickClock(1.0)
    tick.read()
    clock.now += 10.5  # el procesamiento se detuvo 10 segundos
    assert tick.read()[:2] == (True, 2)  # un solo aviso, no diez
    assert tick.read()[0] is False
    clock.now += 0.2
    assert tick.read()[0] is False  # el siguiente cae en el segundo 11, no en 12
    clock.now += 0.4
    assert tick.read()[0] is True


def test_tick_interval_is_never_zero_or_negative():
    assert TickClock(0).interval > 0 and TickClock(-5).interval > 0


def test_tick_node_declaration_and_static_run():
    cls = REGISTRY.require("input.tick")
    assert cls.is_source and [o.name for o in cls.outputs] == ["tick", "count", "time"]
    g = Graph(REGISTRY)
    node = g.add_node("input.tick")
    assert run(g).outputs[node.id] == {"tick": False, "count": 0, "time": 0.0}  # sin errores


def test_tick_keeps_realtime_running_without_a_camera():
    g = Graph(REGISTRY)
    tick = g.add_node("input.tick", params={"interval": 0.01})
    session = RealtimeSession(ExecutionPlan.from_graph(g))
    try:
        assert session.target_interval == pytest.approx(1 / 60)
        ticks = []
        for _ in range(40):
            result = session.step()
            assert result is not None and result.ok
            ticks.append(result.outputs[tick.id]["tick"])
        assert ticks[0] is True and any(ticks)
        assert result.outputs[tick.id]["count"] >= 1
    finally:
        session.close()


def test_tick_node_changes_reopen_the_source():
    g = Graph(REGISTRY)
    tick = g.add_node("input.tick", params={"interval": 5.0, "at_start": False})
    session = RealtimeSession(ExecutionPlan.from_graph(g))
    try:
        assert session.step().outputs[tick.id]["tick"] is False
        g.set_param(tick.id, "interval", 0.01)
        session.set_plan(ExecutionPlan.from_graph(g))
        assert session._sources[tick.id][1].interval == 0.01
    finally:
        session.close()


def test_exported_script_with_a_tick_runs_and_stops(tmp_path, image_path):
    g = Graph(REGISTRY)
    tick = g.add_node("input.tick", params={"interval": 0.05})
    load = g.add_node("input.load_image", params={"path": image_path, "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    out = tmp_path / "o.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(tick.id, "time", thr.id, "thresh")
    g.add_link(thr.id, "image", save.id, "image")
    code, proc = run_script(tmp_path, g, "--max-frames", "4")
    assert proc.returncode == 0, proc.stderr
    assert "import time" in code and "class TickClock" in code and out.exists()
