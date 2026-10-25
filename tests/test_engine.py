"""Motor de ejecución y nodos reales de OpenCV (sin Qt)."""

import cv2
import numpy as np
import pytest

from palantir_nodes.core.graph import Graph
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
    cv2.rectangle(img, (10, 10), (40, 40), (255, 255, 255), -1)
    cv2.circle(img, (60, 30), 12, (0, 0, 255), -1)
    path = tmp_path / "ñandú.png"  # ruta con caracteres no ASCII
    ok, buf = cv2.imencode(".png", img)
    assert ok
    buf.tofile(str(path))
    return str(path)


def run(graph, executor=None, **ctx):
    executor = executor or Executor()
    return executor.run(ExecutionPlan.from_graph(graph), ExecContext(**ctx))


def chain(g, image_path, *type_ids):
    """Load Image → nodos encadenados por su primera entrada/salida de imagen."""
    prev = g.add_node("input.load_image", params={"path": image_path})
    prev_out = "image"
    ids = [prev.id]
    for type_id in type_ids:
        node = g.add_node(type_id)
        g.add_link(prev.id, prev_out, node.id, node.definition.inputs[0].name)
        prev, prev_out = node, node.definition.outputs[0].name if node.definition.outputs else ""
        ids.append(node.id)
    return ids


def test_load_and_process_chain(g, image_path):
    ids = chain(g, image_path, "image.grayscale", "image.gaussian_blur", "output.image_viewer")
    result = run(g)
    assert result.ok, (result.errors, result.blocked)
    assert result.outputs[ids[0]]["width"] == 80
    assert result.outputs[ids[1]]["image"].ndim == 2
    assert result.images[ids[3]].shape == (60, 80)  # el visor expone su entrada


def test_second_run_is_fully_cached(g, image_path):
    chain(g, image_path, "image.grayscale", "image.canny")
    ex = Executor()
    first = run(g, ex)
    second = run(g, ex)
    assert len(first.computed) == 3 and not first.cached
    assert not second.computed and len(second.cached) == 3


def test_changing_param_invalidates_only_affected_nodes(g, image_path):
    load, gray, blur, canny = chain(
        g, image_path, "image.grayscale", "image.gaussian_blur", "image.canny"
    )
    other = g.add_node("input.number")
    ex = Executor()
    run(g, ex)
    g.set_param(blur, "ksize", 9)
    result = run(g, ex)
    assert result.computed == {blur, canny}
    assert {load, gray, other.id} <= result.cached


def test_changing_default_value_invalidates_downstream(g):
    a = g.add_node("input.number")
    add = g.add_node("math.add", input_values={"b": 1.0})
    g.add_link(a.id, "value", add.id, "a")
    ex = Executor()
    assert run(g, ex).outputs[add.id]["result"] == 1.5
    g.set_input_value(add.id, "b", 4.0)
    result = run(g, ex)
    assert result.outputs[add.id]["result"] == 4.5
    assert result.cached == {a.id}


def test_error_is_isolated_to_node_and_downstream(g, image_path):
    broken = g.add_node("input.load_image", params={"path": "no_existe.png"})
    gray = g.add_node("image.grayscale")
    g.add_link(broken.id, "image", gray.id, "image")
    # rama independiente
    n = g.add_node("input.number", params={"value": 2.0})
    mult = g.add_node("math.multiply", input_values={"b": 3.0})
    g.add_link(n.id, "value", mult.id, "a")

    result = run(g)
    assert "No existe el archivo" in result.errors[broken.id]
    assert gray.id in result.blocked and gray.id not in result.errors
    assert result.outputs[mult.id]["result"] == 6.0


def test_invalid_image_file_reports_error(g, tmp_path):
    bad = tmp_path / "roto.png"
    bad.write_bytes(b"esto no es una imagen")
    node = g.add_node("input.load_image", params={"path": str(bad)})
    result = run(g)
    assert "no es una imagen válida" in result.errors[node.id]


def test_empty_path_and_missing_required_input(g):
    load = g.add_node("input.load_image")
    gray = g.add_node("image.grayscale")
    result = run(g)
    assert "ningún archivo" in result.errors[load.id]
    assert "Falta conectar" in result.errors[gray.id]


def test_failing_node_is_not_cached_and_recovers(g, image_path):
    load = g.add_node("input.load_image", params={"path": "x.png"})
    ex = Executor()
    assert load.id in run(g, ex).errors
    g.set_param(load.id, "path", image_path)
    assert run(g, ex).ok


def test_file_change_on_disk_invalidates_cache(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    ex = Executor()
    run(g, ex)
    img = np.full((10, 10, 3), 7, np.uint8)
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(image_path)
    result = run(g, ex)
    assert result.outputs[load.id]["width"] == 10


def test_division_by_zero_reports_error(g):
    div = g.add_node("math.divide", input_values={"a": 1.0, "b": 0.0})
    assert "cero" in run(g).errors[div.id]


def test_implicit_conversion_between_types(g):
    i = g.add_node("input.integer", params={"value": 3})
    add = g.add_node("math.add", input_values={"b": 0.5})
    g.add_link(i.id, "value", add.id, "a")
    assert run(g).outputs[add.id]["result"] == 3.5


def test_cached_arrays_are_read_only(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    arr = run(g).outputs[load.id]["image"]
    assert not arr.flags.writeable


def test_save_image_only_with_side_effects(g, image_path, tmp_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    out = tmp_path / "salida ñ.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(load.id, "image", save.id, "image")
    ex = Executor()
    assert run(g, ex, side_effects=False).ok and not out.exists()
    assert run(g, ex, side_effects=True).ok and out.exists()
    # no se sirve desde la caché: una ejecución explícita vuelve a escribir
    out.unlink()
    run(g, ex, side_effects=True)
    assert out.exists()
    saved = cv2.imdecode(np.fromfile(str(out), np.uint8), cv2.IMREAD_COLOR)
    assert saved.shape == (60, 80, 3)


def test_save_image_errors(g, image_path):
    load = g.add_node("input.load_image", params={"path": image_path})
    save = g.add_node("output.save_image", params={"path": "sin_extension"})
    g.add_link(load.id, "image", save.id, "image")
    assert "extensión" in run(g).errors[save.id]


def test_stale_cache_entries_are_dropped(g):
    n = g.add_node("input.number")
    ex = Executor()
    run(g, ex)
    g.remove_node(n.id)
    run(g, ex)
    assert not ex._cache


# -- humo de todos los nodos con una imagen sintética ----------------------------------

SAMPLE = np.zeros((40, 50, 3), np.uint8)
cv2.rectangle(SAMPLE, (5, 5), (30, 30), (200, 100, 50), -1)
SAMPLE.flags.writeable = False
GRAY = cv2.cvtColor(np.asarray(SAMPLE), cv2.COLOR_BGR2GRAY)
MASK = (GRAY > 0).astype(np.uint8) * 255
CONTOURS = tuple(cv2.findContours(MASK, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2])

NODE_INPUTS = {
    "image.grayscale": {"image": SAMPLE},
    "image.gaussian_blur": {"image": SAMPLE},
    "image.median_blur": {"image": SAMPLE},
    "image.threshold": {"image": SAMPLE},
    "image.adaptive_threshold": {"image": SAMPLE},
    "image.canny": {"image": SAMPLE},
    "image.resize": {"image": SAMPLE},
    "image.crop": {"image": SAMPLE},
    "image.rotate": {"image": SAMPLE},
    "image.flip": {"image": SAMPLE},
    "image.hsv": {"image": SAMPLE},
    "image.in_range": {"image": SAMPLE},
    "image.erode": {"image": SAMPLE},
    "image.dilate": {"image": SAMPLE},
    "image.morphology": {"image": SAMPLE},
    "image.find_contours": {"image": MASK},
    "image.draw_contours": {"image": SAMPLE, "contours": CONTOURS},
    "compose.blend": {"factor": 0.5, "image_a": SAMPLE, "image_b": GRAY},
    "compose.add_weighted": {
        "image_a": SAMPLE,
        "image_b": GRAY,
        "alpha": 0.5,
        "beta": 0.5,
        "gamma": 0.0,
    },
    "compose.bitwise_and": {"image_a": SAMPLE, "image_b": GRAY},
    "compose.bitwise_or": {"image_a": SAMPLE, "image_b": GRAY},
    "compose.bitwise_not": {"image": SAMPLE},
    "compose.mask": {"image": SAMPLE, "mask": MASK[:20, :25]},
    "compose.merge_channels": {"blue": GRAY, "green": GRAY, "red": GRAY},
    "compose.split_channels": {"image": SAMPLE},
    "image.convert_color": {"image": SAMPLE},
    "convert.number_to_string": {"value": 3.14159},
    "convert.string_to_number": {"text": "2,5"},
    "convert.integer_to_float": {"value": 4},
    "convert.float_to_integer": {"value": 2.5},
    "convert.to_json": {"value": [1.5, (2, 3.25)]},
    "convert.json_value": {"json": '{"a": [1, 2]}'},
    "color.rgb_to_hsv": {"color": (200, 40, 90)},
    "color.hsv_to_rgb": {"hsv": (10.0, 200.0, 180.0)},
}


def test_every_builtin_node_is_covered_and_implemented(registry):
    ignored = {t for t in registry._types if t.startswith(("input.", "math.", "output."))}
    assert set(NODE_INPUTS) == set(registry._types) - ignored
    for cls in registry:
        assert cls.is_implemented(), cls.type_id


@pytest.mark.parametrize("type_id", sorted(NODE_INPUTS))
def test_node_process_defaults(registry, type_id):
    cls = registry.require(type_id)
    out = cls().process(ExecContext(), dict(NODE_INPUTS[type_id]), cls.default_params())
    assert set(out) == {s.name for s in cls.outputs}
    for spec in cls.outputs:
        value = out[spec.name]
        if spec.type.value == "Image":
            assert isinstance(value, np.ndarray) and value.dtype == np.uint8 and value.size > 0


def test_source_images_not_mutated_by_nodes(registry):
    before = SAMPLE.copy()
    for type_id, inputs in NODE_INPUTS.items():
        cls = registry.require(type_id)
        cls().process(ExecContext(), dict(inputs), cls.default_params())
    assert np.array_equal(SAMPLE, before)


@pytest.mark.parametrize("type_id", sorted(NODE_INPUTS))
def test_nodes_reject_invalid_images(registry, type_id):
    cls = registry.require(type_id)
    bad = {
        name: (None if isinstance(v, np.ndarray) else v) for name, v in NODE_INPUTS[type_id].items()
    }
    if not any(v is None for v in bad.values()):
        pytest.skip("sin entradas de imagen")
    with pytest.raises((ValueError, TypeError)) as exc:
        cls().process(ExecContext(), bad, cls.default_params())
    assert isinstance(exc.value, ValueError)  # mensaje legible, no un fallo interno


def test_node_behaviour_samples(registry):
    def proc(type_id, inputs, **params):
        cls = registry.require(type_id)
        return cls().process(ExecContext(), inputs, {**cls.default_params(), **params})

    assert proc("image.crop", {"image": SAMPLE}, x=10, y=10, width=100, height=100)[
        "image"
    ].shape == (30, 40, 3)
    with pytest.raises(ValueError, match="fuera de la imagen"):
        proc("image.crop", {"image": SAMPLE}, x=500)
    assert proc("image.resize", {"image": SAMPLE}, mode="size", width=20, height=10)[
        "image"
    ].shape == (10, 20, 3)
    assert proc("image.rotate", {"image": SAMPLE}, angle=90, expand=True)["image"].shape[:2] == (
        50,
        40,
    )
    out = proc("image.find_contours", {"image": MASK})
    assert out["count"] == 1
    assert (
        proc(
            "image.in_range",
            {"image": SAMPLE},
            use_hsv=False,
            lower=(0, 0, 0),
            upper=(255, 255, 255),
        )["mask"].min()
        == 255
    )
    b, g, r = (
        proc("compose.split_channels", {"image": SAMPLE})[k] for k in ("blue", "green", "red")
    )
    assert (b.max(), g.max(), r.max()) == (200, 100, 50)
    masked = proc("compose.mask", {"image": SAMPLE, "mask": MASK})["image"]
    assert masked[35, 45].sum() == 0 and masked[10, 10].sum() > 0
    assert proc("math.compare", {"a": 2.0, "b": 1.0}, op="gt")["result"] is True
    assert (
        proc(
            "math.map_range",
            {"value": 0.5, "from_min": 0.0, "from_max": 1.0, "to_min": 0.0, "to_max": 255.0},
        )["result"]
        == 127.5
    )
