"""Nodos personalizados: ejecución, normalización de salidas, exportación y biblioteca."""

import json
import subprocess
import sys

import cv2
import numpy as np
import pytest

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.graph import Graph, GraphEventKind
from palantir_nodes.core.types import SocketType as T
from palantir_nodes.customnodes.library import CustomNodeLibrary, CustomNodeValidationError
from palantir_nodes.customnodes.runtime import coerce_results
from palantir_nodes.customnodes.spec import CustomNodeSpec, slugify
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.categories import get_category
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.persistence import ProjectData, dump, embedded_custom_nodes, load

BRILLO = '''
def brillo(imagen: Image, cantidad: int = 40, modo: Literal["suma", "resta"] = "suma") -> Image:
    """Cambia el brillo."""
    signo = 1 if modo == "suma" else -1
    return np.clip(imagen.astype(np.int16) + signo * cantidad, 0, 255).astype(np.uint8)
'''


@pytest.fixture
def registry():
    return load_builtin_nodes().copy()  # copia: los nodos de cada prueba no se filtran a las demás


@pytest.fixture
def lib(registry, tmp_path):
    return CustomNodeLibrary(registry, tmp_path / "custom_nodes.json")


@pytest.fixture
def image_path(tmp_path):
    img = np.random.default_rng(5).integers(0, 200, (30, 40, 3), dtype=np.uint8)
    path = tmp_path / "entrada ñ.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


def run(graph, executor=None, **ctx):
    return (executor or Executor()).run(ExecutionPlan.from_graph(graph), ExecContext(**ctx))


def read_png(path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)


def pipeline(registry, image_path, type_id, tmp_path, name="out.png", *, params=None, values=None):
    """Load Image -> nodo personalizado -> Save Image (por su primera salida de imagen)."""
    g = Graph(registry)
    load_node = g.add_node("input.load_image", params={"path": image_path})
    node = g.add_node(type_id, params=params or {}, input_values=values or {})
    first = next(s for s in node.definition.inputs if s.type is T.IMAGE)
    g.add_link(load_node.id, "image", node.id, first.name)
    out = tmp_path / name
    save = g.add_node("output.save_image", params={"path": str(out)})
    image_output = next(o for o in node.definition.outputs if o.type is T.IMAGE)
    g.add_link(node.id, image_output.name, save.id, "image")
    return g, node, out


# -- normalización de salidas ---------------------------------------------------------------------


def test_image_results_are_normalised_to_uint8():
    out = coerce_results(np.array([[0.4, 254.6], [300.0, -5.0]]), ("Image",), "x")[0]
    assert out.dtype == np.uint8 and out.tolist() == [[0, 255], [255, 0]]
    assert coerce_results(np.array([[True, False]]), ("Image",), "x")[0].tolist() == [[255, 0]]
    squeezed = coerce_results(np.zeros((3, 4, 1), np.uint8), ("Image",), "x")[0]
    assert squeezed.shape == (3, 4)
    already = np.zeros((2, 2, 3), np.uint8)
    assert coerce_results(already, ("Image",), "x")[0] is already  # sin copias innecesarias


@pytest.mark.parametrize(
    "value,message",
    [
        ("no soy imagen", "debe ser una imagen"),
        (None, "debe ser una imagen"),
        (np.zeros((0, 4), np.uint8), "forma no válida"),
        (np.zeros((4, 4, 2), np.uint8), "forma no válida"),
        (np.zeros((4,), np.uint8), "forma no válida"),
    ],
)
def test_invalid_images_are_rejected_with_the_node_name(value, message):
    with pytest.raises(ValueError, match=f"Mi nodo: .*{message}"):
        coerce_results(value, ("Image",), "Mi nodo")


def test_scalar_results_are_converted():
    assert coerce_results(np.float32(2.5), ("Float",), "x") == (2.5,)
    assert coerce_results(True, ("Float",), "x") == (1.0,)
    assert coerce_results(np.int64(7), ("Integer",), "x") == (7,)
    assert coerce_results(3.0, ("Integer",), "x") == (3,)
    assert coerce_results(np.bool_(True), ("Boolean",), "x") == (True,)
    assert coerce_results(0, ("Boolean",), "x") == (False,)
    assert coerce_results("hola", ("String",), "x") == ("hola",)
    assert coerce_results([300, 5.4, -3], ("Color",), "x") == ((255, 5, 0),)
    assert coerce_results(np.array([1, 2]), ("Vector2",), "x") == ((1.0, 2.0),)
    assert coerce_results((1, 2, 3), ("Vector3",), "x") == ((1.0, 2.0, 3.0),)
    sentinel = object()
    assert coerce_results(sentinel, ("Any",), "x") == (sentinel,)
    assert coerce_results(None, (), "x") == ()


@pytest.mark.parametrize(
    "kind,value,message",
    [
        ("Float", "abc", "debe ser un número decimal"),
        ("Float", [1, 2], "debe ser un número decimal"),
        ("Integer", 3.5, "debe ser un entero"),
        ("Integer", "3", "debe ser un entero"),
        ("Boolean", 2, "debe ser verdadero o falso"),
        ("Boolean", "sí", "debe ser verdadero o falso"),
        ("String", 5, "debe ser un texto"),
        ("Color", 5, "una secuencia de 3 números"),
        ("Color", (1, 2), "necesita 3 valores"),
        ("Vector2", (1, 2, 3), "necesita 2 valores"),
    ],
)
def test_wrong_scalar_results_explain_what_was_expected(kind, value, message):
    with pytest.raises(ValueError, match=message):
        coerce_results(value, (kind,), "Mi nodo")


def test_multiple_outputs_must_match_the_declared_count():
    assert coerce_results((np.zeros((2, 2), np.uint8), 3), ("Image", "Integer"), "x")[1] == 3
    with pytest.raises(ValueError, match="debe devolver 2 valores y devolvió 3"):
        coerce_results((1, 2, 3), ("Integer", "Integer"), "x")
    with pytest.raises(ValueError, match="devolvió int"):
        coerce_results(5, ("Integer", "Integer"), "x")
    with pytest.raises(ValueError, match="la salida 2 debe ser un entero"):
        coerce_results((1, "x"), ("Integer", "Integer"), "x")


# -- el nodo en el motor ------------------------------------------------------------------------


def test_node_class_is_built_from_the_code(lib, registry):
    spec = lib.create("Brillo", "Mis filtros", BRILLO)
    cls = registry.require(spec.id)
    assert spec.id == "custom.brillo" and cls.label == "Brillo" and cls.category == "Mis filtros"
    assert [(i.name, i.type) for i in cls.inputs] == [("imagen", T.IMAGE), ("cantidad", T.INTEGER)]
    assert cls.input("cantidad").default == 40 and cls.input("imagen").default is None
    assert [(p.name, p.options) for p in cls.params] == [
        ("modo", (("suma", "suma"), ("resta", "resta")))
    ]
    assert [(o.name, o.type) for o in cls.outputs] == [("result", T.IMAGE)]
    assert cls.description == "Cambia el brillo." and cls.cacheable and cls.is_implemented()
    assert get_category("Mis filtros").color  # la categoría nueva existe con color propio
    assert "Mis filtros" in registry.by_category()


def test_image_node_processes_in_the_engine(lib, registry, image_path, tmp_path):
    spec = lib.create("Brillo", "Mis filtros", BRILLO)
    g, node, out = pipeline(registry, image_path, spec.id, tmp_path, values={"cantidad": 25})
    assert run(g, side_effects=True).ok
    original = cv2.imdecode(np.fromfile(image_path, np.uint8), cv2.IMREAD_COLOR)
    expected = np.clip(original.astype(np.int16) + 25, 0, 255).astype(np.uint8)
    assert np.array_equal(read_png(out), expected)
    out.unlink()
    g.set_param(node.id, "modo", "resta")  # la lista desplegable llega a la función
    run(g, side_effects=True)
    assert np.array_equal(
        read_png(out), np.clip(original.astype(np.int16) - 25, 0, 255).astype(np.uint8)
    )


def test_scalar_nodes_chain_with_builtin_parameter_sockets(lib, registry, image_path):
    spec = lib.create(
        "Mitad", "Mis cálculos", "def mitad(a: float, b: float = 2.0) -> float:\n    return a / b\n"
    )
    g = Graph(registry)
    number = g.add_node("input.number", params={"value": 9.0})
    half = g.add_node(spec.id)
    load_node = g.add_node("input.load_image", params={"path": image_path})
    thr = g.add_node("image.threshold")
    g.add_link(number.id, "value", half.id, "a")
    g.add_link(load_node.id, "image", thr.id, "image")
    g.add_link(half.id, "result", thr.id, "thresh")  # salida del nodo -> parámetro conectable
    result = run(g)
    assert result.ok and result.outputs[half.id]["result"] == 4.5
    assert result.outputs[thr.id]["threshold"] == 4


def test_multiple_outputs_and_optional_inputs(lib, registry):
    code = (
        "def partir(valor: float, extra: Image = None) -> tuple[float, bool, int]:\n"
        "    mitad = valor / 2\n    hay_extra = extra is not None\n    tamano = 0 if extra is None else extra.size\n"
        "    return mitad, hay_extra, tamano\n"
    )
    spec = lib.create("Partir", "Mis cálculos", code)
    cls = registry.require(spec.id)
    assert [o.name for o in cls.outputs] == ["mitad", "hay_extra", "tamano"]
    assert cls.input("extra").optional
    g = Graph(registry)
    node = g.add_node(spec.id, input_values={"valor": 10.0})
    out = run(g).outputs[node.id]
    assert (out["mitad"], out["hay_extra"], out["tamano"]) == (5.0, False, 0)
    gray = g.add_node("input.load_image", params={"path": "x"})  # origen de imagen
    assert g.can_connect(gray.id, "image", node.id, "extra")
    assert not g.can_connect(gray.id, "image", node.id, "valor")


def test_user_errors_report_the_line_in_the_users_code(lib, registry):
    spec = lib.create(
        "Falla",
        "Mis cálculos",
        "def falla(x: int) -> int:\n    y = x\n    raise ValueError('boom')\n    return y\n",
    )
    g = Graph(registry)
    node = g.add_node(spec.id)
    message = run(g).errors[node.id]
    assert "ValueError: boom" in message and "línea 3 del código del nodo" in message


def test_helper_function_errors_point_to_the_innermost_user_line(lib, registry):
    code = (
        "def _dividir(a, b):\n    return a / b\n\n"
        "def calcular(x: float) -> float:\n    return _dividir(1.0, x)\n"
    )
    spec = lib.create("Dividir", "Mis cálculos", code)
    g = Graph(registry)
    node = g.add_node(spec.id, input_values={"x": 0.0})
    message = run(g).errors[node.id]
    assert "ZeroDivisionError" in message and "línea 2" in message


def test_input_images_are_read_only_and_the_error_says_how_to_fix_it(lib, registry, image_path):
    spec = lib.create(
        "Pinta",
        "Mis filtros",
        "def pinta(img: Image) -> Image:\n    img[0, 0] = 255\n    return img\n",
    )
    g = Graph(registry)
    load_node = g.add_node("input.load_image", params={"path": image_path})
    node = g.add_node(spec.id)
    g.add_link(load_node.id, "image", node.id, "img")
    message = run(g).errors[node.id]
    assert "solo lectura" in message and "copy()" in message and "línea 2" in message


def test_wrong_return_type_is_reported_with_the_node_name(lib, registry):
    spec = lib.create("Mala", "Mis cálculos", "def mala(x: int) -> Image:\n    return 'texto'\n")
    g = Graph(registry)
    node = g.add_node(spec.id)
    assert "Mala: la salida debe ser una imagen" in run(g).errors[node.id]


def test_module_level_errors_are_reported_at_first_run(lib, registry):
    spec = lib.create(
        "Importa",
        "Mis cálculos",
        "import modulo_que_no_existe\n\ndef f(x: int) -> int:\n    return x\n",
    )
    g = Graph(registry)
    node = g.add_node(spec.id)
    message = run(g).errors[node.id]
    assert "ModuleNotFoundError" in message and "línea 1" in message


def test_module_code_runs_once_and_keeps_its_state(lib, registry):
    code = (
        "llamadas = []\nCARGAS = []\nCARGAS.append(1)\n\n"
        "def contar(x: int) -> int:\n    llamadas.append(x)\n    return len(llamadas) * 100 + len(CARGAS)\n"
    )
    spec = lib.create("Contar", "Mis cálculos", code, always_run=True)
    g = Graph(registry := lib.registry)
    node = g.add_node(spec.id)
    ex = Executor()
    assert run(g, ex).outputs[node.id]["result"] == 101
    assert run(g, ex).outputs[node.id]["result"] == 201  # el módulo no se vuelve a ejecutar
    assert registry.require(spec.id).cacheable is False


def test_numpy_cv2_math_and_imports_are_available(lib, registry):
    code = (
        "import json\n\n"
        "def usa(x: float) -> str:\n"
        "    arr = np.array([x, 4.0])\n"
        "    return json.dumps([float(np.sqrt(arr[1])), math.floor(x), int(cv2.__version__[0]) > 0])\n"
    )
    spec = lib.create("Usa libs", "Mis cálculos", code)
    g = Graph(registry)
    node = g.add_node(spec.id, input_values={"x": 2.7})
    assert run(g).outputs[node.id]["result"] == "[2.0, 2, true]"


def test_two_nodes_with_the_same_helper_names_do_not_interfere(lib, registry):
    one = lib.create(
        "Uno",
        "Mis cálculos",
        "def _f():\n    return 1\n\ndef uno(x: int) -> int:\n    return _f() + x\n",
    )
    two = lib.create(
        "Dos",
        "Mis cálculos",
        "def _f():\n    return 100\n\ndef dos(x: int) -> int:\n    return _f() + x\n",
    )
    g = Graph(registry)
    a, b = g.add_node(one.id), g.add_node(two.id)
    result = run(g)
    assert (result.outputs[a.id]["result"], result.outputs[b.id]["result"]) == (1, 100)


def test_sink_nodes_only_run_on_explicit_execution_and_are_never_cached(lib, registry, tmp_path):
    target = tmp_path / "salida.txt"
    code = f"def escribir(texto: str = 'hola'):\n    open({str(target)!r}, 'a').write(texto)\n"
    spec = lib.create("Escribir", "Mis salidas", code)
    cls = registry.require(spec.id)
    assert not cls.outputs and not cls.cacheable
    g = Graph(registry)
    g.add_node(spec.id)
    ex = Executor()
    assert (
        run(g, ex, side_effects=False).ok and not target.exists()
    )  # ejecución automática: no actúa
    assert run(g, ex, side_effects=True).ok and target.read_text() == "hola"
    assert run(g, ex, side_effects=True).ok and target.read_text() == "holahola"  # sin caché


def test_caching_follows_edits_to_the_code(lib, registry):
    spec = lib.create("Doble", "Mis cálculos", "def doble(x: int) -> int:\n    return x * 2\n")
    g = Graph(registry)
    node = g.add_node(spec.id, input_values={"x": 4})
    ex = Executor()
    first, second = run(g, ex), run(g, ex)
    assert first.outputs[node.id]["result"] == 8 and node.id in second.cached
    lib.update(
        CustomNodeSpec(
            spec.id, "Doble", "Mis cálculos", "def doble(x: int) -> int:\n    return x * 3\n"
        )
    )
    g.migrate_node_type(spec.id)
    third = run(g, ex)
    assert third.outputs[node.id]["result"] == 12 and node.id in third.computed


def test_custom_sockets_connect_with_builtin_nodes_by_type(lib, registry):
    spec = lib.create("Brillo", "Mis filtros", BRILLO)
    g = Graph(registry)
    custom = g.add_node(spec.id)
    gray = g.add_node("image.grayscale")
    number = g.add_node("input.number")
    integer = g.add_node("input.integer")
    assert g.can_connect(custom.id, "result", gray.id, "image")  # Image -> Image
    assert g.can_connect(integer.id, "value", custom.id, "cantidad")
    assert g.can_connect(number.id, "value", custom.id, "cantidad")  # Float -> Integer (conversión)
    assert not g.can_connect(custom.id, "result", custom.id, "cantidad")


def test_custom_nodes_appear_in_search_and_compatibility(lib, registry):
    lib.create("Brillo", "Mis filtros", BRILLO)
    assert [c.label for c in registry.search("brill")] == ["Brillo"]
    labels = {m.node_type.label for m in registry.compatible_with(T.IMAGE, origin_is_output=True)}
    assert "Brillo" in labels


# -- exportación a Python ----------------------------------------------------------------------


def run_script(tmp_path, code, name="script.py"):
    script = tmp_path / name
    script.write_text(code, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), "--no-show"], capture_output=True, text=True, timeout=120
    )


def generate(graph):
    return CodeGenerator(ExecutionPlan.from_graph(graph), "test").generate()


def test_exported_script_equals_engine_for_an_image_node(lib, registry, image_path, tmp_path):
    spec = lib.create("Brillo", "Mis filtros", BRILLO)
    g, node, out = pipeline(
        registry, image_path, spec.id, tmp_path, params={"modo": "resta"}, values={"cantidad": 33}
    )
    assert run(g, side_effects=True).ok
    engine = read_png(out)
    out.unlink()
    code = generate(g)
    proc = run_script(tmp_path, code)
    assert proc.returncode == 0, proc.stderr
    assert np.array_equal(read_png(out), engine)
    assert "palantir_nodes" not in code and "# Nodo personalizado: Brillo" in code
    assert "coerce_results(" in code and "import numpy as np" in code


def test_exported_script_with_connected_inputs_and_multiple_outputs(
    lib, registry, image_path, tmp_path
):
    code = (
        "def separar(imagen: Image, umbral: float = 100.0, extra: Image = None)"
        " -> tuple[Image, float]:\n"
        "    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)\n"
        "    mascara = (gris > umbral).astype(np.uint8) * 255\n"
        "    peso = float(mascara.mean()) + (0.0 if extra is None else float(extra.mean()))\n"
        "    return mascara, math.sqrt(peso)\n"
    )
    spec = lib.create("Separar", "Mis filtros", code)
    g = Graph(registry)
    load_node = g.add_node("input.load_image", params={"path": image_path})
    node = g.add_node(spec.id)
    number = g.add_node("input.number", params={"value": 120.0})
    mask_out, thr_out = tmp_path / "mask.png", tmp_path / "thr.png"
    save_mask = g.add_node("output.save_image", params={"path": str(mask_out)})
    save_thr = g.add_node("output.save_image", params={"path": str(thr_out)})
    thr = g.add_node("image.threshold")
    g.add_link(load_node.id, "image", node.id, "imagen")
    g.add_link(load_node.id, "image", node.id, "extra")  # entrada opcional conectada
    g.add_link(number.id, "value", node.id, "umbral")
    g.add_link(node.id, "result_1", save_mask.id, "image")
    g.add_link(node.id, "result_2", thr.id, "thresh")  # segunda salida (Float) -> parámetro
    g.add_link(node.id, "result_1", thr.id, "image")
    g.add_link(thr.id, "image", save_thr.id, "image")
    assert run(g, side_effects=True).ok
    engine = [read_png(mask_out), read_png(thr_out)]
    mask_out.unlink()
    thr_out.unlink()
    proc = run_script(tmp_path, generate(g))
    assert proc.returncode == 0, proc.stderr
    for expected, path in zip(engine, (mask_out, thr_out), strict=True):
        assert np.array_equal(read_png(path), expected)


def test_unconnected_optional_input_is_none_in_the_script(lib, registry, tmp_path):
    code = (
        "def f(imagen: Image, otra: Image = None) -> Image:\n"
        "    return imagen if otra is None else otra\n"
    )
    spec = lib.create("Opcional", "Mis filtros", code)
    g = Graph(registry)
    load_node = g.add_node("input.load_image", params={"path": "x.png"})
    node = g.add_node(spec.id)
    save = g.add_node("output.save_image", params={"path": str(tmp_path / "o.png")})
    g.add_link(load_node.id, "image", node.id, "imagen")
    g.add_link(node.id, "result", save.id, "image")
    assert "otra=None" in generate(g)


def test_sink_custom_node_is_exported_and_acts_in_the_script(lib, registry, image_path, tmp_path):
    target = tmp_path / "guardada.png"
    code = f"def guardar(imagen: Image):\n    cv2.imwrite({str(target)!r}, imagen)\n"
    spec = lib.create("Guardar con cv2", "Mis salidas", code)
    g = Graph(registry)
    load_node = g.add_node("input.load_image", params={"path": image_path})
    node = g.add_node(spec.id)
    g.add_link(load_node.id, "image", node.id, "imagen")
    proc = run_script(tmp_path, generate(g))
    assert proc.returncode == 0, proc.stderr
    assert read_png(target).shape == (30, 40, 3)


def test_a_node_used_twice_is_defined_once_and_different_nodes_do_not_clash(
    lib, registry, image_path, tmp_path
):
    one = lib.create(
        "Uno", "X", "def _f():\n    return 1\n\ndef uno(x: int) -> int:\n    return _f() + x\n"
    )
    two = lib.create(
        "Dos", "X", "def _f():\n    return 100\n\ndef dos(x: int) -> int:\n    return _f() + x\n"
    )
    g = Graph(registry)
    a1 = g.add_node(one.id, input_values={"x": 1})
    a2 = g.add_node(one.id, input_values={"x": 2})
    b = g.add_node(two.id, input_values={"x": 3})
    load_node = g.add_node("input.load_image", params={"path": image_path})
    thr = g.add_node("image.threshold")
    g.add_link(load_node.id, "image", thr.id, "image")
    g.add_link(a1.id, "result", thr.id, "thresh")
    save = g.add_node("output.save_image", params={"path": str(tmp_path / "o.png")})
    g.add_link(thr.id, "image", save.id, "image")
    # los otros dos nodos solo alimentan un segundo umbral para que se exporten
    thr2 = g.add_node("image.threshold")
    g.add_link(load_node.id, "image", thr2.id, "image")
    g.add_link(a2.id, "result", thr2.id, "thresh")
    g.add_link(b.id, "result", thr2.id, "maxval")
    save2 = g.add_node("output.save_image", params={"path": str(tmp_path / "o2.png")})
    g.add_link(thr2.id, "image", save2.id, "image")
    code = generate(g)
    assert code.count("def make_uno():") == 1 and code.count("def make_dos():") == 1
    proc = run_script(tmp_path, code)
    assert proc.returncode == 0, proc.stderr
    assert run(g, side_effects=True).ok
    assert np.array_equal(read_png(tmp_path / "o2.png"), read_png(tmp_path / "o2.png"))


def test_script_errors_name_the_custom_node(lib, registry, tmp_path):
    spec = lib.create("Falla", "X", "def falla(x: int) -> int:\n    raise ValueError('boom')\n")
    g = Graph(registry)
    node = g.add_node(spec.id)
    thr = g.add_node("image.threshold")
    load_node = g.add_node("input.load_image", params={"path": "x.png"})
    save = g.add_node("output.save_image", params={"path": str(tmp_path / "o.png")})
    g.add_link(node.id, "result", thr.id, "thresh")
    g.add_link(load_node.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", save.id, "image")
    proc = run_script(tmp_path, generate(g))
    assert (
        proc.returncode != 0 and "Error en el nodo 'Falla'" in proc.stderr and "boom" in proc.stderr
    )


# -- biblioteca ----------------------------------------------------------------------------------


def test_ids_come_from_the_name_and_do_not_change_when_renaming(lib):
    a = lib.create("Mi filtro ñ", "X", BRILLO)
    b = lib.create("Mi filtro n", "X", BRILLO)
    assert a.id == "custom.mi_filtro_n" and b.id == "custom.mi_filtro_n_2"
    renamed = CustomNodeSpec(a.id, "Otro nombre", "Y", a.code)
    lib.update(renamed)
    assert lib.registry.require(a.id).label == "Otro nombre" and a.id in lib.entries
    assert "Mi filtro ñ" not in {c.label for c in lib.registry}
    assert slugify("   ") == "nodo" and slugify("Ñandú – Test") == "nandu_test"


@pytest.mark.parametrize(
    "label,category,code,message",
    [
        ("", "X", BRILLO, "necesita un nombre"),
        ("  Con espacios ", "X", BRILLO, "espacios en los extremos"),
        ("x" * 61, "X", BRILLO, "más de 60"),
        ("Grayscale", "X", BRILLO, "Ya existe un nodo llamado 'Grayscale'"),
        ("gaussian blur", "X", BRILLO, "Ya existe un nodo llamado"),
        ("Bien", "", BRILLO, "Elige una categoría"),
        ("Bien", "y" * 41, BRILLO, "más de 40"),
        ("Bien", "X", "x = 1", "ninguna función pública"),
        ("Bien", "X", "def f(x: lista):\n    pass", "tipo no soportado 'lista'"),
    ],
)
def test_invalid_definitions_are_rejected_without_side_effects(lib, label, category, code, message):
    before = len(lib.registry)
    with pytest.raises(CustomNodeValidationError, match=message):
        lib.create(label, category, code)
    assert len(lib.registry) == before and not lib.entries and not lib.path.exists()


def test_names_must_be_unique_among_custom_nodes_too(lib):
    lib.create("Brillo", "X", BRILLO)
    with pytest.raises(CustomNodeValidationError, match="Ya existe"):
        lib.create("brillo", "X", BRILLO)
    other = lib.create("Otro", "X", BRILLO)
    with pytest.raises(CustomNodeValidationError, match="Ya existe"):
        lib.update(CustomNodeSpec(other.id, "BRILLO", "X", BRILLO))
    lib.update(
        CustomNodeSpec(other.id, "Otro", "X", BRILLO + "\n# cambio\n")
    )  # su propio nombre: bien


def test_update_replaces_the_registered_type_and_remove_unregisters_it(lib, registry):
    spec = lib.create("Brillo", "X", BRILLO)
    old = registry.require(spec.id)
    lib.update(CustomNodeSpec(spec.id, "Brillo", "X", "def f(a: float) -> float:\n    return a\n"))
    assert registry.require(spec.id) is not old and [
        i.name for i in registry.require(spec.id).inputs
    ] == ["a"]
    lib.remove(spec.id)
    assert spec.id not in registry and spec.id not in lib.entries
    with pytest.raises(KeyError):
        lib.remove(spec.id)
    with pytest.raises(KeyError):
        lib.update(spec)


def test_duplicate_copies_the_node_with_a_new_name_and_id(lib):
    spec = lib.create("Brillo", "X", BRILLO, "desc", True)
    copy = lib.duplicate(spec.id)
    assert copy.label == "Brillo (copia)" and copy.id != spec.id
    assert (copy.code, copy.category, copy.description, copy.always_run) == (
        BRILLO,
        "X",
        "desc",
        True,
    )
    assert lib.duplicate(spec.id).label == "Brillo (copia 2)"


def test_library_is_saved_and_loaded_with_every_field(lib, registry, tmp_path):
    lib.create("Brillo", "Mis filtros", BRILLO, "Descripción ñ", True)
    lib.create("Mitad", "Mis cálculos", "def m(a: float) -> float:\n    return a / 2\n")
    saved = json.loads(lib.path.read_text(encoding="utf-8"))
    assert saved["format"] == "palantir-nodes-custom-library" and len(saved["nodes"]) == 2
    assert "Descripción ñ" in lib.path.read_text(encoding="utf-8")

    fresh_registry = load_builtin_nodes().copy()
    fresh = CustomNodeLibrary(fresh_registry, lib.path)
    assert fresh.load() == []
    assert set(fresh.entries) == set(lib.entries) and {s.label for s in fresh.entries.values()} == {
        "Brillo",
        "Mitad",
    }
    assert (
        fresh.get("custom.brillo").always_run
        and fresh.get("custom.brillo").description == "Descripción ñ"
    )
    assert (
        "custom.brillo" in fresh_registry and not fresh_registry.require("custom.brillo").cacheable
    )
    assert not [f for f in tmp_path.glob("*.tmp")]


def test_entries_with_broken_code_are_kept_but_not_registered(lib, registry, tmp_path):
    lib.create("Bien", "X", BRILLO)
    data = json.loads(lib.path.read_text(encoding="utf-8"))
    data["nodes"].append(
        {"id": "custom.roto", "label": "Roto", "category": "X", "code": "def f(x: lista):\n  pass"}
    )
    lib.path.write_text(json.dumps(data), encoding="utf-8")
    fresh_registry = load_builtin_nodes().copy()
    fresh = CustomNodeLibrary(fresh_registry, lib.path)
    warnings = fresh.load()
    assert len(warnings) == 1 and "Roto" in warnings[0] and "errores" in warnings[0]
    assert "custom.roto" in fresh.entries and "custom.roto" in fresh.broken
    assert "custom.roto" not in fresh_registry and "custom.bien" in fresh_registry
    fresh.save()  # guardar no pierde la entrada rota
    assert "custom.roto" in lib.path.read_text(encoding="utf-8")
    fresh.update(
        CustomNodeSpec("custom.roto", "Roto", "X", "def f(x: int) -> int:\n    return x\n")
    )
    assert "custom.roto" in fresh_registry and not fresh.broken  # corregirlo lo registra


@pytest.mark.parametrize("content", ["{ no es json", "[]", '{"nodes": 5}', "", "null"])
def test_corrupt_library_files_do_not_stop_loading(registry, tmp_path, content):
    path = tmp_path / "lib.json"
    path.write_text(content, encoding="utf-8")
    lib = CustomNodeLibrary(registry, path)
    warnings = lib.load()
    assert len(warnings) == 1 and not lib.entries


def test_invalid_and_repeated_entries_are_skipped_individually(registry, tmp_path):
    good = {
        "id": "custom.a",
        "label": "A",
        "category": "X",
        "code": "def a(x: int) -> int:\n    return x\n",
    }
    path = tmp_path / "lib.json"
    path.write_text(
        json.dumps(
            {
                "nodes": [
                    good,
                    "texto",
                    {"id": "otra.cosa", "label": "B", "category": "X", "code": "def b(): pass"},
                    {"id": "custom.c", "label": "", "category": "X", "code": "x"},
                    {**good, "label": "A repetida"},
                ]
            }
        ),
        encoding="utf-8",
    )
    lib = CustomNodeLibrary(registry, path)
    warnings = lib.load()
    assert list(lib.entries) == ["custom.a"] and len(warnings) == 4


def test_missing_library_is_empty_and_unwritable_location_raises_oserror(registry, tmp_path):
    lib = CustomNodeLibrary(registry, tmp_path / "no_existe.json")
    assert lib.load() == [] and not lib.entries
    blocker = tmp_path / "archivo"
    blocker.write_text("x")
    blocked = CustomNodeLibrary(registry, blocker / "lib.json")
    with pytest.raises(OSError):
        blocked.create("Brillo", "X", BRILLO)
    assert "custom.brillo" in registry  # se aplicó en esta sesión aunque no se pudo guardar


def test_import_spec_for_nodes_from_a_project(lib, registry):
    spec = CustomNodeSpec("custom.traido", "Traído", "Z", "def t(x: int) -> int:\n    return x\n")
    assert lib.import_spec(spec) and "custom.traido" in registry
    assert not lib.import_spec(spec)  # mismo id: ya estaba
    clash = CustomNodeSpec("custom.otro", "Traído", "Z", "def o(x: int) -> int:\n    return x\n")
    assert lib.import_spec(clash) and lib.entries["custom.otro"].label == "Traído (2)"
    with pytest.raises(CustomNodeValidationError):
        lib.import_spec(CustomNodeSpec("custom.malo", "Malo", "Z", "def f(x: lista):\n    pass"))
    assert "custom.malo" not in lib.entries


def test_categories_include_custom_ones_and_get_distinct_colors(lib):
    lib.create("A", "Cat nueva 1", "def a(x: int) -> int:\n    return x\n")
    lib.create("B", "Cat nueva 2", "def b(x: int) -> int:\n    return x\n")
    assert {"Cat nueva 1", "Cat nueva 2", "Imagen"} <= set(lib.categories())
    assert get_category("Cat nueva 1").color != get_category("Cat nueva 2").color
    assert get_category("Cat nueva 1").order >= 50  # después de las categorías integradas


# -- el grafo cuando cambia un tipo --------------------------------------------------------------


def test_migrating_keeps_matching_values_and_drops_incompatible_links(lib, registry):
    spec = lib.create(
        "Mezcla",
        "X",
        "def mezcla(imagen: Image, k: int = 3, modo: Literal['a', 'b'] = 'a', t: float = 1.0) -> Image:\n"
        "    return imagen\n",
    )
    g = Graph(registry)
    load_node = g.add_node("input.load_image")
    node = g.add_node(spec.id, params={"modo": "b"}, input_values={"k": 9, "t": 2.5})
    sink = g.add_node("image.grayscale")
    number = g.add_node("input.number")
    g.add_link(load_node.id, "image", node.id, "imagen")
    g.add_link(number.id, "value", node.id, "t")
    g.add_link(node.id, "imagen", sink.id, "image")
    events = []
    g.subscribe(events.append)

    lib.update(
        CustomNodeSpec(
            spec.id,
            "Mezcla",
            "X",
            "def mezcla(imagen: Image, k: int = 5, modo: Literal['b', 'c'] = 'c') -> int:\n    return k\n",
        )
    )
    notes = g.migrate_node_type(spec.id)
    migrated = g.node(node.id)
    assert migrated.input_values == {"k": 9}  # 'k' se conserva; 't' desapareció
    assert migrated.params == {"modo": "b"}  # 'b' sigue siendo una opción válida
    assert g.link_to_input(node.id, "imagen") is not None  # compatible: se mantiene
    assert g.link_to_input(node.id, "t") is None  # el socket ya no existe
    assert g.link_to_input(sink.id, "image") is None  # Integer -> Image ya no es válido
    assert len(notes) == 2 and any("imagen" in n for n in notes)
    assert events[-1].kind is GraphEventKind.REBUILT


def test_migrating_resets_values_that_became_invalid(lib, registry):
    spec = lib.create(
        "Modo", "X", "def f(modo: Literal['a', 'b'] = 'a') -> str:\n    return modo\n"
    )
    g = Graph(registry)
    node = g.add_node(spec.id, params={"modo": "b"})
    lib.update(
        CustomNodeSpec(
            spec.id, "Modo", "X", "def f(modo: Literal['x', 'y'] = 'y') -> str:\n    return modo\n"
        )
    )
    notes = g.migrate_node_type(spec.id)
    assert g.node(node.id).params["modo"] == "y" and any("valor por defecto" in n for n in notes)


def test_removing_a_type_removes_its_nodes_and_links(lib, registry):
    spec = lib.create("Brillo", "X", BRILLO)
    g = Graph(registry)
    a = g.add_node(spec.id)
    g.add_node(spec.id)
    gray = g.add_node("image.grayscale")
    g.add_link(a.id, "result", gray.id, "image")
    lib.remove(spec.id)
    assert g.remove_nodes_of_type(spec.id) == 2
    assert not g.links and set(g.nodes) == {gray.id} and g.nodes_of_type(spec.id) == []


# -- proyectos -----------------------------------------------------------------------------------


def test_projects_embed_the_definitions_and_read_them_back(lib, registry):
    spec = lib.create("Brillo", "Mis filtros", BRILLO, "desc")
    g = Graph(registry)
    g.add_node(spec.id, params={"modo": "resta"}, input_values={"cantidad": 7})
    doc = json.loads(json.dumps(dump(g, ProjectData(), "t", [spec.to_dict()])))
    assert doc["custom_nodes"][0]["code"] == BRILLO and doc["custom_nodes"][0]["id"] == spec.id
    specs, warnings = embedded_custom_nodes(doc)
    assert not warnings and specs[0].to_dict() == spec.to_dict()
    graph2, project = load(doc, registry)
    assert next(iter(graph2.nodes.values())).input_values == {"cantidad": 7}
    assert project.custom_nodes == [spec.to_dict()]


def test_projects_without_custom_nodes_still_load_and_bad_entries_are_ignored(registry):
    assert embedded_custom_nodes({"format": "x"}) == ([], [])
    assert embedded_custom_nodes({"custom_nodes": 5})[1]
    specs, warnings = embedded_custom_nodes(
        {
            "custom_nodes": [
                {"id": "custom.a", "label": "A", "category": "X", "code": "x"},
                "texto",
                {"id": "no"},
            ]
        }
    )
    assert len(specs) == 1 and len(warnings) == 2


def test_unknown_custom_types_in_a_project_are_preserved_as_unknown_nodes(registry):
    doc = {
        "format": "palantir-nodes",
        "version": 1,
        "nodes": [{"id": "n1", "type_id": "custom.fantasma", "position": [0, 0]}],
        "links": [],
        "custom_nodes": [],
    }
    graph, project = load(doc, registry)
    assert not graph.nodes and project.preserved_nodes[0]["type_id"] == "custom.fantasma"
