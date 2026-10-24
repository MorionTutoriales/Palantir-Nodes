"""Exportación a Python: estructura del script y equivalencia con el motor."""

import ast
import os
import subprocess
import sys

import cv2
import numpy as np
import pytest

from palantir_nodes.codegen import CodeGenerator, ExportError
from palantir_nodes.core.graph import Graph
from palantir_nodes.core.types import IMPLICIT_CONVERSIONS
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.registry import load_builtin_nodes


@pytest.fixture(scope="module")
def registry():
    return load_builtin_nodes()


@pytest.fixture
def g(registry):
    return Graph(registry)


@pytest.fixture
def image_path(tmp_path):
    img = np.zeros((60, 80, 3), np.uint8)
    img[:] = (30, 40, 50)
    cv2.rectangle(img, (10, 10), (40, 40), (255, 255, 255), -1)
    cv2.circle(img, (60, 30), 12, (0, 0, 255), -1)
    cv2.line(img, (0, 55), (79, 5), (0, 200, 0), 3)
    path = tmp_path / "entrada ñ.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


def generate(graph):
    return CodeGenerator(ExecutionPlan.from_graph(graph), "test").generate()


def read(path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)


def run_script(code, tmp_path, *args):
    script = tmp_path / "exportado.py"
    script.write_text(code, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), "--no-show", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def assert_equivalent(graph, tmp_path, outputs):
    """Ejecuta el motor y el script; ambos deben guardar las mismas imágenes."""
    result = Executor().run(ExecutionPlan.from_graph(graph), ExecContext(side_effects=True))
    assert result.ok, (result.errors, result.blocked)
    expected = {p: read(p) for p in outputs}
    for p in outputs:
        p.unlink()
    proc = run_script(generate(graph), tmp_path)
    assert proc.returncode == 0, proc.stderr
    for p in outputs:
        assert p.exists(), p
        got = read(p)
        assert got.shape == expected[p].shape and np.array_equal(got, expected[p]), p.name


# -- estructura del script ---------------------------------------------------------------


def simple_graph(g, image_path, tmp_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    blur = g.add_node("image.gaussian_blur", params={"ksize": 7})
    out = tmp_path / "salida.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    view = g.add_node("output.image_viewer")
    g.add_link(load.id, "image", blur.id, "image")
    g.add_link(blur.id, "image", save.id, "image")
    g.add_link(blur.id, "image", view.id, "image")
    return out


def test_script_structure(g, image_path, tmp_path):
    simple_graph(g, image_path, tmp_path)
    code = generate(g)
    tree = ast.parse(code)
    assert any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body)
    assert 'if __name__ == "__main__":' in code
    assert "import cv2" in code and "import numpy as np" in code
    assert "cv2.GaussianBlur" in code and "(7, 7)" in code
    assert "palantir_nodes" not in code and "PySide6" not in code
    assert "cv2.imshow" in code and "destroyAllWindows" in code


def test_script_runs_without_app_and_saves(g, image_path, tmp_path):
    out = simple_graph(g, image_path, tmp_path)
    proc = run_script(generate(g), tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert read(out).shape == (60, 80, 3)


def test_variable_names_are_unique_and_valid(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    prev = load
    for _ in range(5):
        node = g.add_node("image.gaussian_blur")
        g.add_link(prev.id, "image", node.id, "image")
        prev = node
    view = g.add_node("output.image_viewer")
    g.add_link(prev.id, "image", view.id, "image")
    tree = ast.parse(generate(g))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    assigned = [
        t.id
        for n in ast.walk(main)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name) and t.id != "node"
    ]
    assert len(assigned) == len(set(assigned)) == 6


def test_dead_branches_are_not_exported(g, image_path, tmp_path):
    simple_graph(g, image_path, tmp_path)
    g.add_node("image.canny")  # sin conectar: no alimenta ninguna salida
    assert "Canny" not in generate(g)


def test_error_message_names_the_failing_node(g, image_path, tmp_path):
    simple_graph(g, image_path, tmp_path)
    code = generate(g)
    os.remove(image_path)
    proc = run_script(code, tmp_path)
    assert proc.returncode != 0
    assert "Error en el nodo 'Load Image'" in proc.stderr
    assert "No existe el archivo" in proc.stderr


def test_math_error_is_reported_in_script(g, tmp_path):
    n = g.add_node("math.divide", input_values={"a": 1.0, "b": 0.0})
    load = g.add_node("input.load_image", params={"path": "x.png"})
    aw = g.add_node("compose.add_weighted")
    g.add_link(n.id, "result", aw.id, "alpha")
    g.add_link(load.id, "image", aw.id, "image_a")
    g.add_link(load.id, "image", aw.id, "image_b")
    view = g.add_node("output.image_viewer")
    g.add_link(aw.id, "image", view.id, "image")
    proc = run_script(generate(g), tmp_path)
    assert "Error en el nodo 'Load Image'" in proc.stderr or "División" in proc.stderr


def test_export_rejects_graphs_that_cannot_be_exported(g, image_path):
    with pytest.raises(ExportError, match="nodos de salida"):
        generate(g)

    view = g.add_node("output.image_viewer")
    with pytest.raises(ExportError) as exc:
        generate(g)
    assert "falta conectar" in str(exc.value)
    assert exc.value.problems[0].node_id == view.id

    load = g.add_node("input.load_image")  # sin archivo
    g.add_link(load.id, "image", view.id, "image")
    with pytest.raises(ExportError, match="ningún archivo"):
        generate(g)
    g.set_param(load.id, "path", image_path)
    assert "read_image" in generate(g)

    save = g.add_node("output.save_image")
    g.add_link(load.id, "image", save.id, "image")
    with pytest.raises(ExportError, match="archivo de destino"):
        generate(g)
    g.set_param(save.id, "path", "sin_extension")
    with pytest.raises(ExportError, match="extensión"):
        generate(g)


@pytest.mark.parametrize("pair", list(IMPLICIT_CONVERSIONS.items()), ids=lambda p: p[1].description)
def test_conversion_templates_match_conversions(pair):
    (src, _dst), conv = pair
    samples = {
        "Integer": 3,
        "Float": 2.6,
        "Boolean": True,
        "Color": (10, 300, 0),
        "Vector3": (10.4, 300.2, -3.0),
    }
    value = samples[src.value]
    assert eval(conv.template.format("value"), {"value": value}) == conv.convert(value)  # noqa: S307


# -- equivalencia nodo por nodo ----------------------------------------------------------

CASES = [
    ("image.grayscale", {}),
    ("image.gaussian_blur", {"ksize": 8, "sigma": 1.5}),
    ("image.median_blur", {"ksize": 5}),
    ("image.threshold", {}),
    ("image.threshold", {"otsu": True, "method": "binary_inv"}),
    ("image.adaptive_threshold", {}),
    ("image.adaptive_threshold", {"method": "mean", "type": "binary_inv", "block_size": 8}),
    ("image.canny", {}),
    ("image.canny", {"aperture": "5", "l2_gradient": True}),
    ("image.resize", {}),
    ("image.resize", {"mode": "size", "width": 33, "height": 21, "interpolation": "area"}),
    ("image.crop", {"x": 5, "y": 7, "width": 30, "height": 20}),
    ("image.rotate", {"angle": 30.0}),
    ("image.rotate", {"angle": 33.0, "expand": True, "interpolation": "cubic"}),
    ("image.flip", {"axis": "both"}),
    ("image.hsv", {}),
    ("image.hsv", {"direction": "hsv2bgr"}),
    ("image.in_range", {"lower": (0.0, 50.0, 50.0), "upper": (30.0, 255.0, 255.0)}),
    (
        "image.in_range",
        {"use_hsv": False, "lower": (0.0, 0.0, 100.0), "upper": (50.4, 90.6, 255.0)},
    ),
    ("image.erode", {"ksize": 3, "iterations": 2}),
    ("image.dilate", {"shape": "ellipse"}),
    ("image.morphology", {"op": "gradient", "shape": "cross"}),
    ("image.morphology", {"op": "blackhat", "ksize": 5}),
    ("image.find_contours", {}),
    ("image.draw_contours", {"color": (255, 0, 128), "thickness": -1}),
    ("compose.blend", {"mode": "mix"}),
    ("compose.blend", {"mode": "add"}),
    ("compose.blend", {"mode": "multiply"}),
    ("compose.blend", {"mode": "screen"}),
    ("compose.add_weighted", {}),
    ("compose.bitwise_and", {}),
    ("compose.bitwise_or", {}),
    ("compose.bitwise_not", {}),
    ("compose.mask", {}),
    ("compose.mask", {"invert": True}),
    ("compose.merge_channels", {}),
    ("compose.split_channels", {}),
]


def case_id(case):
    return case[0] + ("" if not case[1] else ":" + ",".join(f"{k}={v}" for k, v in case[1].items()))


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_node_export_equals_engine(g, image_path, tmp_path, case):
    type_id, params = case
    load = g.add_node("input.load_image", params={"path": image_path})
    gray = g.add_node("image.grayscale")
    thr = g.add_node("image.threshold", params={"thresh": 100.0})
    cont = g.add_node("image.find_contours", params={"mode": "list"})
    g.add_link(load.id, "image", gray.id, "image")
    g.add_link(gray.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", cont.id, "image")

    node = g.add_node(type_id, params=params)
    image_inputs = 0
    for spec in node.definition.inputs:
        if spec.type.value == "Image":
            # La segunda imagen es en gris y más pequeña: ejercita match().
            if spec.name == "mask":
                source = (thr.id, "image")
            elif image_inputs == 0 or spec.name in ("blue", "green", "red"):
                source = (load.id, "image")
            else:
                source = (gray.id, "image")
            if node.definition.type_id == "compose.merge_channels":
                source = (gray.id, "image")
            image_inputs += 1
            g.add_link(*source, node.id, spec.name)
        elif spec.type.value == "Any":
            g.add_link(cont.id, "contours", node.id, spec.name)

    outputs = []
    for spec in node.definition.outputs:
        if spec.type.value == "Image":
            path = tmp_path / f"{spec.name}.png"
            save = g.add_node("output.save_image", params={"path": str(path)})
            g.add_link(node.id, spec.name, save.id, "image")
            outputs.append(path)
    if not outputs:  # Find Contours: se comprueba dibujándolos
        draw = g.add_node("image.draw_contours")
        g.add_link(load.id, "image", draw.id, "image")
        g.add_link(node.id, "contours", draw.id, "contours")
        path = tmp_path / "contours.png"
        save = g.add_node("output.save_image", params={"path": str(path)})
        g.add_link(draw.id, "image", save.id, "image")
        outputs.append(path)
    assert_equivalent(g, tmp_path, outputs)


def test_math_scalars_and_conversions_equal_engine(g, image_path, tmp_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    gray = g.add_node("image.grayscale")
    g.add_link(load.id, "image", gray.id, "image")

    a = g.add_node("input.number", params={"value": 0.7})
    b = g.add_node("input.number", params={"value": -0.2})
    add = g.add_node("math.add")
    sub = g.add_node("math.subtract")
    mul = g.add_node("math.multiply", input_values={"b": 0.9})
    div = g.add_node("math.divide", input_values={"b": 4.0})
    clamp = g.add_node("math.clamp", input_values={"min": 0.1, "max": 0.8})
    mapr = g.add_node("math.map_range", params={"clamp": True}, input_values={"to_max": 2.0})
    mn = g.add_node("math.minimum", input_values={"b": 0.6})
    mx = g.add_node("math.maximum", input_values={"b": 0.2})
    cmp = g.add_node("math.compare", params={"op": "ge"})
    integer = g.add_node("input.integer", params={"value": 2})
    g.add_link(a.id, "value", add.id, "a")
    g.add_link(b.id, "value", add.id, "b")
    g.add_link(a.id, "value", sub.id, "a")
    g.add_link(b.id, "value", sub.id, "b")
    g.add_link(add.id, "result", mul.id, "a")
    g.add_link(sub.id, "result", div.id, "a")
    g.add_link(mul.id, "result", clamp.id, "value")
    g.add_link(div.id, "result", mapr.id, "value")
    g.add_link(clamp.id, "result", mn.id, "a")
    g.add_link(mapr.id, "result", mx.id, "a")
    g.add_link(mn.id, "result", cmp.id, "a")
    g.add_link(mx.id, "result", cmp.id, "b")

    aw = g.add_node("compose.add_weighted")
    g.add_link(load.id, "image", aw.id, "image_a")
    g.add_link(gray.id, "image", aw.id, "image_b")
    g.add_link(mn.id, "result", aw.id, "alpha")  # Float
    g.add_link(cmp.id, "result", aw.id, "beta")  # Boolean -> Float
    g.add_link(integer.id, "value", aw.id, "gamma")  # Integer -> Float
    blend = g.add_node("compose.blend")
    g.add_link(mx.id, "result", blend.id, "factor")
    g.add_link(load.id, "image", blend.id, "image_a")
    g.add_link(gray.id, "image", blend.id, "image_b")

    paths = []
    for name, node in (("aw", aw), ("blend", blend)):
        path = tmp_path / f"{name}.png"
        save = g.add_node("output.save_image", params={"path": str(path)})
        g.add_link(node.id, "image", save.id, "image")
        paths.append(path)
    assert_equivalent(g, tmp_path, paths)


def test_load_modes_and_dimensions_equal_engine(g, image_path, tmp_path):
    paths = []
    for mode in ("color", "grayscale", "unchanged"):
        load = g.add_node("input.load_image", params={"path": image_path, "mode": mode})
        path = tmp_path / f"load_{mode}.png"
        save = g.add_node("output.save_image", params={"path": str(path)})
        g.add_link(load.id, "image", save.id, "image")
        paths.append(path)
    load = g.add_node("input.load_image", params={"path": image_path})
    resize = g.add_node("image.resize", params={"mode": "size"})
    crop = g.add_node("image.crop", params={"width": 20, "height": 10})
    g.add_link(load.id, "image", resize.id, "image")
    g.add_link(resize.id, "image", crop.id, "image")
    path = tmp_path / "dims.png"
    save = g.add_node("output.save_image", params={"path": str(path)})
    g.add_link(crop.id, "image", save.id, "image")
    paths.append(path)
    assert_equivalent(g, tmp_path, paths)
    assert "shape[1]" not in generate(g)  # width/height no usados: no se generan
