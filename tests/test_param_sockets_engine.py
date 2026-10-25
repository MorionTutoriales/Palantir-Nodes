"""Parámetros conectables: modelo, motor y exportación a Python (sin interfaz)."""

import subprocess
import sys

import cv2
import numpy as np
import pytest

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.errors import GraphError, RegistryError
from palantir_nodes.core.graph import Graph
from palantir_nodes.core.types import SocketType as T
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.base import Expr, NodeDefinition
from palantir_nodes.nodes.registry import NodeRegistry, load_builtin_nodes
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec


@pytest.fixture(scope="module")
def registry():
    return load_builtin_nodes()


@pytest.fixture
def g(registry):
    return Graph(registry)


# -- ParamSpec ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,expected",
    [
        (ParamKind.INT, T.INTEGER),
        (ParamKind.FLOAT, T.FLOAT),
        (ParamKind.BOOL, T.BOOLEAN),
        (ParamKind.COLOR, T.COLOR),
        (ParamKind.VECTOR2, T.VECTOR2),
        (ParamKind.VECTOR3, T.VECTOR3),
        (ParamKind.ENUM, None),
        (ParamKind.STRING, None),
        (ParamKind.FILE_PATH, None),
    ],
)
def test_socket_type_depends_on_the_parameter_kind(kind, expected):
    spec = ParamSpec("p", kind, None)
    assert spec.socket_type is expected
    assert (spec.as_input() is None) == (expected is None)


def test_connectable_false_removes_the_socket():
    spec = ParamSpec("p", ParamKind.FLOAT, 0.0, connectable=False)
    assert spec.socket_type is None and spec.as_input() is None


def test_param_as_input_keeps_label_range_and_default():
    spec = ParamSpec("k", ParamKind.INT, 5, label="Kernel", minimum=1, maximum=99, step=2)
    socket = spec.as_input()
    assert isinstance(socket, InputSpec)
    assert (socket.name, socket.type, socket.default) == ("k", T.INTEGER, 5)
    assert (socket.display_label, socket.minimum, socket.maximum) == ("Kernel", 1, 99)


COERCE_SPECS = [
    ParamSpec("i", ParamKind.INT, 5, minimum=1, maximum=99),
    ParamSpec("i", ParamKind.INT, 0),
    ParamSpec("f", ParamKind.FLOAT, 0.0, minimum=0.0, maximum=255.0),
    ParamSpec("f", ParamKind.FLOAT, 0.0, minimum=-100, maximum=100),
    ParamSpec("f", ParamKind.FLOAT, 0.0),
    ParamSpec("b", ParamKind.BOOL, False),
    ParamSpec("c", ParamKind.COLOR, (0, 0, 0)),
    ParamSpec("v", ParamKind.VECTOR3, (0.0, 0.0, 0.0), minimum=0, maximum=255),
    ParamSpec("v", ParamKind.VECTOR2, (0.0, 0.0)),
]
COERCE_SAMPLES = {
    ParamKind.INT: [0, 5, 3.0, 2.5, 3.5, -7, 1000, 7.6, True],
    ParamKind.FLOAT: [0, 1, 2.5, -3.2, 254.9, 300, 1e9, True],
    ParamKind.BOOL: [True, False],
    ParamKind.COLOR: [(0, 0, 0), (10, 300, -5), (255.0, 128.4, 1.6), [1, 2, 3]],
    ParamKind.VECTOR3: [(0, 0, 0), (10.5, 300.2, -3.0), (1, 2, 3), [4.5, 5.5, 6.5]],
    ParamKind.VECTOR2: [(0, 0), (1.5, -2.5), [9, 8]],
}


@pytest.mark.parametrize(
    "spec", COERCE_SPECS, ids=lambda s: f"{s.kind.value}:{s.minimum}:{s.maximum}"
)
def test_coerce_expr_is_equivalent_to_coerce(spec):
    for value in COERCE_SAMPLES[spec.kind]:
        expected = spec.coerce(value)
        got = eval(spec.coerce_expr("v"), {"v": value})  # noqa: S307
        assert got == expected and type(got) is type(expected), (value, got, expected)


def test_coerce_expr_rejects_kinds_without_socket():
    with pytest.raises(ValueError):
        ParamSpec("e", ParamKind.ENUM, "a", options=(("a", "A"),)).coerce_expr("x")


# -- NodeDefinition ----------------------------------------------------------------------


def test_input_lookup_includes_connectable_params(registry):
    blur = registry.require("image.gaussian_blur")
    assert [s.name for s in blur.inputs] == ["image"]
    assert [s.name for s in blur.socket_inputs()] == ["image", "ksize", "sigma"]
    assert blur.input("sigma").type is T.FLOAT and blur.input("sigma").default == 0.0
    assert blur.input("nada") is None
    assert [p.name for p in blur.connectable_params()] == ["ksize", "sigma"]
    threshold = registry.require("image.threshold")
    assert threshold.input("method") is None  # un enumerado no tiene socket
    assert registry.require("input.number").connectable_params() == ()


def test_name_clash_between_input_and_connectable_param_is_rejected():
    class Clash(NodeDefinition):
        type_id = "test.clash"
        label = "Clash"
        category = "Test"
        inputs = (InputSpec("amount", T.FLOAT, default=0.0),)
        outputs = (OutputSpec("out", T.FLOAT),)
        params = (ParamSpec("amount", ParamKind.FLOAT, 1.0),)

    with pytest.raises(RegistryError, match="comparten nombre"):
        NodeRegistry().register(Clash)

    class Fine(Clash):
        type_id = "test.fine"
        params = (ParamSpec("amount", ParamKind.FLOAT, 1.0, connectable=False),)

    NodeRegistry().register(Fine)  # sin socket no hay conflicto


def test_expr_inserts_its_code_but_cannot_be_evaluated():
    e = Expr("sigma")
    assert repr(e) == "sigma" and str(e) == "sigma"
    with pytest.raises(TypeError, match="al ejecutar el script"):
        bool(e)
    with pytest.raises(TypeError):
        e + 1  # noqa: B018


# -- motor: el valor conectado sustituye al escrito ---------------------------------------


@pytest.fixture
def image_path(tmp_path):
    img = np.zeros((60, 80, 3), np.uint8)
    img[:] = (30, 40, 50)
    cv2.rectangle(img, (10, 10), (40, 40), (255, 255, 255), -1)
    cv2.circle(img, (60, 30), 12, (0, 0, 255), -1)
    cv2.line(img, (0, 55), (79, 5), (0, 200, 0), 3)
    noise = np.random.default_rng(3).integers(0, 40, img.shape, dtype=np.uint8)
    img = cv2.add(img, noise)
    path = tmp_path / "entrada ñ.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


def run(graph, executor=None, **ctx):
    return (executor or Executor()).run(ExecutionPlan.from_graph(graph), ExecContext(**ctx))


def test_connected_value_replaces_the_written_one(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    blur = g.add_node("image.gaussian_blur", params={"ksize": 5, "sigma": 0.0})
    g.add_link(load.id, "image", blur.id, "image")
    plain = run(g).outputs[blur.id]["image"]

    number = g.add_node("input.number", params={"value": 6.0})
    g.add_link(number.id, "value", blur.id, "sigma")
    driven = run(g).outputs[blur.id]["image"]
    assert not np.array_equal(plain, driven)

    expected = cv2.GaussianBlur(
        cv2.imdecode(np.fromfile(image_path, np.uint8), cv2.IMREAD_COLOR), (5, 5), 6.0
    )
    assert np.array_equal(driven, expected)


def test_disconnecting_restores_the_written_value(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    blur = g.add_node("image.gaussian_blur", params={"sigma": 0.0})
    g.add_link(load.id, "image", blur.id, "image")
    number = g.add_node("input.number", params={"value": 6.0})
    link = g.add_link(number.id, "value", blur.id, "sigma")
    ex = Executor()
    driven = run(g, ex).outputs[blur.id]["image"]
    g.remove_link(link.id)
    restored = run(g, ex).outputs[blur.id]["image"]
    assert not np.array_equal(driven, restored)
    assert g.node(blur.id).params["sigma"] == 0.0  # el valor escrito nunca se perdió


def test_upstream_change_recomputes_only_dependents(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    gray = g.add_node("image.grayscale")
    blur = g.add_node("image.gaussian_blur")
    other = g.add_node("image.flip")
    number = g.add_node("input.number", params={"value": 2.0})
    g.add_link(load.id, "image", gray.id, "image")
    g.add_link(gray.id, "image", blur.id, "image")
    g.add_link(load.id, "image", other.id, "image")
    g.add_link(number.id, "value", blur.id, "sigma")
    ex = Executor()
    run(g, ex)
    g.set_param(number.id, "value", 4.0)
    second = run(g, ex)
    assert second.computed == {number.id, blur.id}
    assert {load.id, gray.id, other.id} <= second.cached


def test_connected_values_are_converted_and_clamped_like_written_ones(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    blur = g.add_node("image.gaussian_blur")
    g.add_link(load.id, "image", blur.id, "image")
    number = g.add_node("input.number", params={"value": 200.7})  # Float -> Integer, fuera de rango
    g.add_link(number.id, "value", blur.id, "ksize")
    ex = Executor()
    driven = run(g, ex).outputs[blur.id]["image"]
    g.set_param(number.id, "value", 99.0)
    assert np.array_equal(driven, run(g, ex).outputs[blur.id]["image"])  # 200.7 -> 99 (máximo)

    g.set_param(number.id, "value", 4.4)  # -> 4 -> kernel par 5
    four = run(g, ex).outputs[blur.id]["image"]
    g.remove_link(next(iter(g.links_from_output(number.id, "value"))).id)
    g.set_param(blur.id, "ksize", 4)
    assert np.array_equal(four, run(g, ex).outputs[blur.id]["image"])


def test_an_error_upstream_blocks_the_driven_node_only(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    blur = g.add_node("image.gaussian_blur")
    flip = g.add_node("image.flip")
    div = g.add_node("math.divide", input_values={"a": 1.0, "b": 0.0})
    g.add_link(load.id, "image", blur.id, "image")
    g.add_link(load.id, "image", flip.id, "image")
    g.add_link(div.id, "result", blur.id, "sigma")
    result = run(g)
    assert "cero" in result.errors[div.id] and blur.id in result.blocked
    assert flip.id in result.outputs


def test_ranges_on_connected_values_are_enforced(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    thr = g.add_node("image.threshold")
    g.add_link(load.id, "image", thr.id, "image")
    number = g.add_node("input.number", params={"value": 9999.0})
    g.add_link(number.id, "value", thr.id, "thresh")
    assert run(g).outputs[thr.id]["threshold"] == 255.0  # recortado al máximo del parámetro


def test_color_and_vector_and_bool_sockets(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    rng = g.add_node("image.in_range", params={"use_hsv": False})
    g.add_link(load.id, "image", rng.id, "image")
    color = g.add_node("input.color", params={"color": (10, 20, 30)})
    g.add_link(color.id, "color", rng.id, "lower")  # Color -> Vector3 (conversión implícita)
    vec = g.add_node("input.vector3", params={"value": (255.0, 255.0, 255.0)})
    g.add_link(vec.id, "vector", rng.id, "upper")
    flag = g.add_node("input.boolean", params={"value": False})
    g.add_link(flag.id, "value", rng.id, "use_hsv")
    driven = run(g).outputs[rng.id]["mask"]

    g2 = Graph(g.registry)
    load2 = g2.add_node("input.load_image", params={"path": image_path})
    rng2 = g2.add_node(
        "image.in_range",
        params={"use_hsv": False, "lower": (10.0, 20.0, 30.0), "upper": (255.0, 255.0, 255.0)},
    )
    g2.add_link(load2.id, "image", rng2.id, "image")
    assert np.array_equal(driven, run(g2).outputs[rng2.id]["mask"])


def test_a_comparison_can_drive_a_boolean_parameter(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    mask_src = g.add_node("image.threshold", params={"thresh": 100.0})
    mask = g.add_node("compose.mask")
    cmp = g.add_node("math.compare", params={"op": "gt"}, input_values={"a": 2.0, "b": 1.0})
    g.add_link(load.id, "image", mask_src.id, "image")
    g.add_link(load.id, "image", mask.id, "image")
    g.add_link(mask_src.id, "image", mask.id, "mask")
    keep = run(g).outputs[mask.id]["image"]
    g.add_link(cmp.id, "result", mask.id, "invert")  # 2 > 1 -> invertir
    inverted = run(g).outputs[mask.id]["image"]
    assert not np.array_equal(keep, inverted)
    g.set_param(cmp.id, "op", "lt")  # falso: vuelve a no invertir
    assert np.array_equal(run(g).outputs[mask.id]["image"], keep)


def test_vector_nodes_produce_their_value(g):
    v2 = g.add_node("input.vector2", params={"value": (1.5, -2.0)})
    v3 = g.add_node("input.vector3", params={"value": (1.0, 2.0, 3.5)})
    result = run(g)
    assert result.outputs[v2.id]["vector"] == (1.5, -2.0)
    assert result.outputs[v3.id]["vector"] == (1.0, 2.0, 3.5)


# -- equivalencia nodo por nodo: conectado == escrito == script ---------------------------

SOURCE_FOR = {
    T.FLOAT: ("input.number", "value"),
    T.INTEGER: ("input.integer", "value"),
    T.BOOLEAN: ("input.boolean", "value"),
    T.COLOR: ("input.color", "color"),
    T.VECTOR3: ("input.vector3", "value"),
    T.VECTOR2: ("input.vector2", "value"),
}

# (nodo, parámetros base, parámetro conectado, valor)
PARAM_CASES = [
    ("compose.mask", {}, "invert", True),
    ("image.gaussian_blur", {}, "ksize", 9),
    ("image.gaussian_blur", {"ksize": 5}, "sigma", 2.5),
    ("image.median_blur", {}, "ksize", 7),
    ("image.threshold", {}, "thresh", 90.0),
    ("image.threshold", {}, "maxval", 200.0),
    ("image.threshold", {}, "otsu", True),
    ("image.adaptive_threshold", {}, "maxval", 200.0),
    ("image.adaptive_threshold", {}, "block_size", 15),
    ("image.adaptive_threshold", {}, "c", 5.0),
    ("image.canny", {}, "threshold1", 50.0),
    ("image.canny", {}, "threshold2", 120.0),
    ("image.canny", {}, "l2_gradient", True),
    ("image.resize", {}, "scale", 0.7),
    ("image.resize", {"mode": "size"}, "width", 33),
    ("image.resize", {"mode": "size"}, "height", 21),
    ("image.crop", {}, "x", 5),
    ("image.crop", {}, "y", 7),
    ("image.crop", {"width": 30}, "width", 25),
    ("image.crop", {"height": 30}, "height", 20),
    ("image.rotate", {}, "angle", 25.0),
    ("image.rotate", {"angle": 33.0}, "expand", True),
    ("image.in_range", {}, "use_hsv", False),
    ("image.in_range", {}, "lower", (0.0, 50.0, 50.0)),
    ("image.in_range", {}, "upper", (30.0, 255.0, 255.0)),
    ("image.erode", {}, "ksize", 5),
    ("image.erode", {}, "iterations", 2),
    ("image.dilate", {}, "ksize", 5),
    ("image.dilate", {}, "iterations", 2),
    ("image.morphology", {}, "ksize", 5),
    ("image.morphology", {}, "iterations", 2),
    ("image.draw_contours", {}, "color", (255, 0, 128)),
    ("image.draw_contours", {}, "thickness", 3),
    ("image.draw_contours", {}, "index", 0),
]


def test_the_matrix_covers_every_connectable_parameter_except_map_range(registry):
    covered = {(t, p) for t, _, p, _ in PARAM_CASES} | {("math.map_range", "clamp")}
    existing = {(cls.type_id, p.name) for cls in registry for p in cls.connectable_params()}
    assert covered == existing


def build(g, type_id, image_path, out_dir, params, connect=None):
    """Imagen -> nodo (con entradas de apoyo) -> Save Image por cada salida de imagen."""
    load = g.add_node("input.load_image", params={"path": image_path})
    gray = g.add_node("image.grayscale")
    thr = g.add_node("image.threshold", params={"thresh": 100.0})
    cont = g.add_node("image.find_contours", params={"mode": "list"})
    g.add_link(load.id, "image", gray.id, "image")
    g.add_link(gray.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", cont.id, "image")

    node = g.add_node(type_id, params=params)
    first_image = True
    for spec in node.definition.inputs:
        if spec.type is T.IMAGE:
            source = (
                (thr.id, "image")
                if spec.name == "mask"
                else ((load.id, "image") if first_image else (gray.id, "image"))
            )
            first_image = False
            g.add_link(*source, node.id, spec.name)
        elif spec.type is T.ANY:
            g.add_link(cont.id, "contours", node.id, spec.name)
    for name, value in (connect or {}).items():
        socket_type = node.definition.input(name).type
        src_type, src_param = SOURCE_FOR[socket_type]
        src = g.add_node(src_type, params={src_param: value})
        g.add_link(src.id, _first_output(src), node.id, name)
    outputs = []
    for spec in node.definition.outputs:
        if spec.type is T.IMAGE:
            path = out_dir / f"{type_id}_{spec.name}_{len(list(out_dir.iterdir()))}.png"
            save = g.add_node("output.save_image", params={"path": str(path)})
            g.add_link(node.id, spec.name, save.id, "image")
            outputs.append(path)
    return outputs


def _first_output(node):
    return node.definition.outputs[0].name  # NodeInstance.definition


def read_png(path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)


def run_save(graph, outputs):
    result = run(graph, side_effects=True)
    assert result.ok, (result.errors, result.blocked)
    arrays = [read_png(p) for p in outputs]
    for p in outputs:
        p.unlink()
    return arrays


def case_id(case):
    return f"{case[0].split('.')[-1]}-{case[2]}"


@pytest.mark.parametrize("case", PARAM_CASES, ids=case_id)
def test_connected_equals_written_value(registry, image_path, tmp_path, case):
    type_id, base, name, value = case
    connected_dir, written_dir = tmp_path / "c", tmp_path / "w"
    connected_dir.mkdir()
    written_dir.mkdir()
    g1, g2 = Graph(registry), Graph(registry)
    out1 = build(g1, type_id, image_path, connected_dir, base, connect={name: value})
    out2 = build(g2, type_id, image_path, written_dir, {**base, name: value})
    for a, b in zip(run_save(g1, out1), run_save(g2, out2), strict=True):
        assert a.shape == b.shape and np.array_equal(a, b)


@pytest.mark.parametrize("case", PARAM_CASES, ids=case_id)
def test_exported_script_equals_engine_with_connected_value(registry, image_path, tmp_path, case):
    type_id, base, name, value = case
    g = Graph(registry)
    outputs = build(g, type_id, image_path, tmp_path, base, connect={name: value})
    engine = run_save(g, outputs)
    code = CodeGenerator(ExecutionPlan.from_graph(g), "test").generate()
    compile(code, "script", "exec")
    script = tmp_path / "exportado.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    for expected, path in zip(engine, outputs, strict=True):
        got = read_png(path)
        assert got.shape == expected.shape and np.array_equal(got, expected)


def map_range_graph(g, image_path, out_dir, *, clamp):
    """Map Range -> umbral de Threshold: el recorte del parámetro ``clamp`` se nota en la salida."""
    load = g.add_node("input.load_image", params={"path": image_path})
    mapr = g.add_node(
        "math.map_range",
        input_values={
            "value": 1.5,
            "from_min": 0.0,
            "from_max": 1.0,
            "to_min": 0.0,
            "to_max": 100.0,
        },
    )
    thr = g.add_node("image.threshold")
    path = out_dir / f"mr_{clamp}.png"
    save = g.add_node("output.save_image", params={"path": str(path)})
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(mapr.id, "result", thr.id, "thresh")
    g.add_link(thr.id, "image", save.id, "image")
    flag = g.add_node("input.boolean", params={"value": clamp})
    g.add_link(flag.id, "value", mapr.id, "clamp")
    return path


@pytest.mark.parametrize("clamp", [True, False])
def test_boolean_parameter_of_map_range_in_engine_and_script(registry, image_path, tmp_path, clamp):
    g = Graph(registry)
    path = map_range_graph(g, image_path, tmp_path, clamp=clamp)
    engine = run_save(g, [path])[0]
    script = tmp_path / "mr.py"
    script.write_text(CodeGenerator(ExecutionPlan.from_graph(g)).generate(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert np.array_equal(read_png(path), engine)
    other = Graph(registry)
    other_path = map_range_graph(other, image_path, tmp_path, clamp=not clamp)
    assert not np.array_equal(engine, run_save(other, [other_path])[0])  # el parámetro sí importa


def test_conversion_chain_is_exported_faithfully(registry, image_path, tmp_path):
    """Integer -> Float -> Integer: las conversiones del motor se repiten en el script."""
    g = Graph(registry)
    load = g.add_node("input.load_image", params={"path": image_path})
    integer = g.add_node("input.integer", params={"value": 7})
    add = g.add_node("math.add", input_values={"b": 0.6})  # Integer -> Float (a); 7.6
    blur = g.add_node("image.gaussian_blur")
    out = tmp_path / "salida.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(integer.id, "value", add.id, "a")
    g.add_link(add.id, "result", blur.id, "ksize")  # Float -> Integer (redondeo): 8 -> kernel 9
    g.add_link(load.id, "image", blur.id, "image")
    g.add_link(blur.id, "image", save.id, "image")
    engine = run_save(g, [out])[0]
    script = tmp_path / "chain.py"
    code = CodeGenerator(ExecutionPlan.from_graph(g)).generate()
    assert "odd(" in code and "int(round(" in code
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert np.array_equal(read_png(out), engine)
    expected = cv2.GaussianBlur(
        cv2.imdecode(np.fromfile(image_path, np.uint8), cv2.IMREAD_COLOR), (9, 9), 0.0
    )
    assert np.array_equal(engine, expected)


def test_exporting_every_connectable_parameter_never_trips_on_expr(registry, image_path, tmp_path):
    """Si algún nodo decidiera algo en tiempo de generación con un parámetro conectado,
    ``Expr`` lanzaría TypeError: aquí se exporta cada combinación para detectarlo."""
    for type_id, base, name, value in PARAM_CASES:
        g = Graph(registry)
        build(g, type_id, image_path, tmp_path, base, connect={name: value})
        code = CodeGenerator(ExecutionPlan.from_graph(g)).generate()
        compile(code, type_id, "exec")


def test_unused_graph_features_keep_working_for_unconnected_params(registry, image_path, tmp_path):
    g = Graph(registry)
    out = build(g, "image.gaussian_blur", image_path, tmp_path, {"ksize": 7, "sigma": 1.5})
    code = CodeGenerator(ExecutionPlan.from_graph(g)).generate()
    assert "(7, 7)" in code and "1.5" in code and "odd(" not in code  # igual que antes
    assert out


def test_linking_to_a_param_socket_is_validated_like_any_input(g):
    blur = g.add_node("image.gaussian_blur")
    load = g.add_node("input.load_image")
    number = g.add_node("input.number")
    assert g.can_connect(number.id, "value", blur.id, "sigma")
    assert not g.can_connect(load.id, "image", blur.id, "sigma")  # Image -> Float
    with pytest.raises(GraphError):
        g.add_link(load.id, "image", blur.id, "sigma")
    link = g.add_link(number.id, "value", blur.id, "sigma")
    other = g.add_node("input.number")
    assert g.can_connect(other.id, "value", blur.id, "sigma")  # reemplazaría a la existente
    assert g.link_to_input(blur.id, "sigma") == link


def test_non_connectable_params_have_no_socket(g):
    number = g.add_node("input.number")
    other = g.add_node("input.number")
    assert not g.can_connect(other.id, "value", number.id, "value")  # el valor del nodo Number
    thr = g.add_node("image.threshold")
    assert not g.can_connect(number.id, "value", thr.id, "method")  # enumerados: sin socket


def test_registering_a_custom_node_with_param_socket(g):
    registry = NodeRegistry()

    @register_node_in(registry)
    class Scale(NodeDefinition):
        type_id = "test.scale"
        label = "Scale"
        category = "Test"
        outputs = (OutputSpec("out", T.FLOAT),)
        params = (ParamSpec("factor", ParamKind.FLOAT, 2.0),)

        def process(self, ctx, inputs, params):
            return {"out": params["factor"] * 10}

    @register_node_in(registry)
    class Const(NodeDefinition):
        type_id = "test.const"
        label = "Const"
        category = "Test"
        outputs = (OutputSpec("v", T.FLOAT),)
        params = (ParamSpec("value", ParamKind.FLOAT, 5.0, connectable=False),)

        def process(self, ctx, inputs, params):
            return {"v": params["value"]}

    graph = Graph(registry)
    scale = graph.add_node("test.scale")
    const = graph.add_node("test.const")
    assert run(graph).outputs[scale.id]["out"] == 20.0
    graph.add_link(const.id, "v", scale.id, "factor")
    assert run(graph).outputs[scale.id]["out"] == 50.0


def register_node_in(registry):
    def decorator(cls):
        return registry.register(cls)

    return decorator
