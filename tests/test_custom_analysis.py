"""Análisis estático del código de un nodo personalizado."""

import os

import pytest

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.customnodes.analysis import analyze


def params(analysis):
    return {p.name: p for p in analysis.params}


def outputs(analysis):
    return [(o.name, o.socket_type) for o in analysis.outputs]


def test_detects_function_inputs_and_output():
    a = analyze(
        '''
def filtro(imagen: Image, umbral: float = 0.5, pasos: int = 3, activo: bool = True) -> Image:
    """Filtra la imagen."""
    return imagen
'''
    )
    assert a.ok and a.function_name == "filtro" and a.description == "Filtra la imagen."
    p = params(a)
    assert p["imagen"].socket_type is T.IMAGE and not p["imagen"].optional
    assert (p["umbral"].socket_type, p["umbral"].default) == (T.FLOAT, 0.5)
    assert (p["pasos"].socket_type, p["pasos"].default) == (T.INTEGER, 3)
    assert (p["activo"].socket_type, p["activo"].default) == (T.BOOLEAN, True)
    assert outputs(a) == [("imagen", T.IMAGE)]  # nombrada por la variable que se devuelve
    assert not a.errors and not a.warnings


@pytest.mark.parametrize(
    "annotation,expected",
    [
        ("int", T.INTEGER),
        ("float", T.FLOAT),
        ("bool", T.BOOLEAN),
        ("str", T.STRING),
        ("Image", T.IMAGE),
        ("np.ndarray", T.IMAGE),
        ("numpy.ndarray", T.IMAGE),
        ("ndarray", T.IMAGE),
        ("cv2.Mat", T.IMAGE),
        ("np.typing.NDArray[np.uint8]", T.IMAGE),
        ("Color", T.COLOR),
        ("Vector2", T.VECTOR2),
        ("Vector3", T.VECTOR3),
        ("Any", T.ANY),
        ("object", T.ANY),
        ("tuple[float, float]", T.VECTOR2),
        ("tuple[int, int]", T.VECTOR2),
        ("Tuple[float, float, float]", T.VECTOR3),
        ("tuple[int, int, int]", T.COLOR),
        ('"Image"', T.IMAGE),
    ],
)
def test_annotation_to_socket_type(annotation, expected):
    a = analyze(f"def f(x: {annotation}):\n    pass\n")
    assert a.ok, a.errors
    assert params(a)["x"].socket_type is expected


@pytest.mark.parametrize(
    "annotation,message",
    [
        ("list", "tipo no soportado 'list'"),
        ("dict[str, int]", "tipo no soportado"),
        ("Optional[int]", "tipo no soportado"),
        ("tuple[str, str]", "tuple solo se admite"),
        ("tuple[float]", "tuple solo se admite"),
        ("tuple[float, float, float, float]", "tuple solo se admite"),
        ("Literal[1, 2]", "Literal solo admite textos"),
        ("Literal['a', 'a']", "opciones repetidas"),
        ("MiClase", "tipo no soportado 'MiClase'"),
    ],
)
def test_unsupported_annotations_explain_the_supported_types(annotation, message):
    a = analyze(f"def f(x: {annotation}):\n    pass\n")
    assert not a.ok and any(message in e.message for e in a.errors)
    assert a.errors[0].line == 1


def test_scalar_parameters_without_default_get_a_neutral_editable_value():
    a = analyze(
        "def f(i: int, x: float, b: bool, s: str, c: Color, v2: Vector2, v3: Vector3):\n    pass\n"
    )
    p = params(a)
    assert (p["i"].default, p["x"].default, p["b"].default, p["s"].default) == (0, 0.0, False, "")
    assert (p["c"].default, p["v2"].default, p["v3"].default) == (
        (0, 0, 0),
        (0.0, 0.0),
        (0.0, 0.0, 0.0),
    )


def test_defaults_are_coerced_to_the_declared_type():
    a = analyze("def f(x: float = 3, c: Color = (300, 5, -4), v: Vector2 = (1, 2)):\n    pass\n")
    p = params(a)
    assert p["x"].default == 3.0 and isinstance(p["x"].default, float)
    assert p["c"].default == (255, 5, 0)
    assert p["v"].default == (1.0, 2.0)


@pytest.mark.parametrize(
    "signature,message",
    [
        ("x: int = 'a'", "no es Integer"),
        ("x: float = 'a'", "no es Float"),
        ("v: Vector3 = (1, 2)", "no es Vector3"),
        ("x: int = foo()", "debe ser un literal"),
        ("x: float = y", "debe ser un literal"),
        ("img: Image = 5", "solo admite None"),
        ("v: Any = 0", "solo admite None"),
    ],
)
def test_invalid_defaults_are_reported_with_the_parameter_name(signature, message):
    a = analyze(f"def f({signature}):\n    pass\n")
    assert not a.ok and any(message in e.message for e in a.errors)


def test_none_default_makes_image_inputs_optional_and_warns_for_scalars():
    a = analyze(
        "def f(a: Image, mascara: Image = None, x: float = None, c: Any = None):\n    pass\n"
    )
    p = params(a)
    assert not p["a"].optional and p["mascara"].optional and p["c"].optional
    assert p["x"].default == 0.0 and any("None no es válido" in w.message for w in a.warnings)
    assert a.ok


def test_literal_becomes_a_dropdown():
    a = analyze(
        "def f(modo: Literal['suma', 'resta'] = 'resta',"
        " otro: Literal['x', 'y'] = 'x'):\n    pass\n"
    )
    p = params(a)
    assert p["modo"].kind == "enum" and p["modo"].options == ("suma", "resta")
    assert p["modo"].default == "resta" and p["otro"].default == "x"
    a = analyze("def f(modo: Literal['a', 'b']):\n    pass\n")
    assert params(a)["modo"].default == "a"  # sin valor por defecto: la primera opción
    a = analyze("def f(modo: Literal['a', 'b'] = 'z'):\n    pass\n")
    assert not a.ok and "no está entre" in a.errors[0].message


def test_types_are_inferred_from_defaults_when_not_annotated():
    a = analyze(
        "def f(a=True, b=3, c=2.5, d='hola', e=(0, 128, 255),"
        " f=(1.5, 2.5, 3.5), g=(1.0, 2.0)):\n    pass\n"
    )
    p = params(a)
    assert [p[n].socket_type for n in "abcdefg"] == [
        T.BOOLEAN,
        T.INTEGER,
        T.FLOAT,
        T.STRING,
        T.COLOR,
        T.VECTOR3,
        T.VECTOR2,
    ]
    assert not a.warnings


def test_untyped_parameters_without_default_are_any_with_a_hint():
    a = analyze("def f(imagen):\n    pass\n")
    assert params(a)["imagen"].socket_type is T.ANY
    assert any("no tiene tipo" in w.message and "imagen: Image" in w.message for w in a.warnings)


# -- función del nodo ------------------------------------------------------------------------


def test_the_last_public_function_is_the_node_and_underscored_ones_are_helpers():
    a = analyze(
        "def _ayuda(x):\n    return x\n\ndef primero(a: int):\n    pass\n\ndef _otro():\n    pass\n"
    )
    assert a.function_name == "primero" and not a.warnings
    a = analyze("def a(x: int):\n    pass\n\ndef b(y: float):\n    pass\n")
    assert a.function_name == "b" and any("última" in w.message for w in a.warnings)
    assert list(params(a)) == ["y"]


@pytest.mark.parametrize(
    "code,message",
    [
        ("", "Escribe el código"),
        ("   \n\n", "Escribe el código"),
        ("x = 1\n", "ninguna función pública"),
        ("def _solo_privada():\n    pass\n", "ninguna función pública"),
        ("import math\n", "ninguna función pública"),
    ],
)
def test_code_without_a_function_explains_what_to_write(code, message):
    a = analyze(code)
    assert not a.ok and message in a.errors[0].message


def test_syntax_errors_report_the_line():
    a = analyze("def f(x: int):\n    return (x +\n")
    assert not a.ok and a.errors[0].message.startswith("sintaxis") and a.errors[0].line
    a = analyze("def f(x: int)\n    pass\n")
    assert a.errors[0].line == 1


def test_errors_only_found_inside_the_factory_are_mapped_to_user_lines():
    a = analyze("import os\n\ndef f(x: int):\n    from os import *\n    return x\n")
    assert not a.ok and a.errors[0].line == 4  # la línea del usuario, no la de la fábrica


@pytest.mark.parametrize(
    "code,message",
    [
        ("from __future__ import annotations\ndef f(x: int):\n    pass\n", "__future__"),
        ("def f(*args):\n    pass\n", "*args"),
        ("def f(**kw):\n    pass\n", "**kwargs"),
        ("def f(a, /, b):\n    pass\n", "solo posicionales"),
        ("async def f(x: int):\n    pass\n", "async"),
    ],
)
def test_unsupported_constructs_are_rejected(code, message):
    a = analyze(code)
    assert not a.ok and any(message in e.message for e in a.errors)


def test_keyword_only_parameters_are_supported():
    a = analyze("def f(a: int, *, b: float = 2.0):\n    pass\n")
    assert a.ok and list(params(a)) == ["a", "b"] and params(a)["b"].default == 2.0


def test_analysis_never_executes_the_code(tmp_path):
    marker = tmp_path / "ejecutado.txt"
    code = (
        f"open({str(marker)!r}, 'w').write('x')\n"
        "import os\nos.environ['PALANTIR_ANALISIS'] = '1'\n"
        "raise SystemExit(3)\n"
        "def f(x: int):\n    return x\n"
    )
    a = analyze(code)
    assert a.ok and not marker.exists() and "PALANTIR_ANALISIS" not in os.environ


# -- salidas ----------------------------------------------------------------------------------


def test_output_name_comes_from_the_returned_variable():
    a = analyze("def f(img: Image) -> Image:\n    mascara = img\n    return mascara\n")
    assert outputs(a) == [("mascara", T.IMAGE)]
    a = analyze("def f(img: Image) -> Image:\n    return img.copy()\n")
    assert outputs(a) == [("result", T.IMAGE)]
    a = analyze(
        "def f(img: Image, flag: bool) -> Image:\n    if flag:\n        return a\n    return b\n"
    )
    assert outputs(a) == [("result", T.IMAGE)]  # return con nombres distintos: nombre genérico


def test_tuple_return_creates_several_named_outputs():
    a = analyze(
        "def f(img: Image) -> tuple[Image, float, int]:\n"
        "    mask, area = img, 1.0\n    n = 3\n    return mask, area, n\n"
    )
    assert outputs(a) == [("mask", T.IMAGE), ("area", T.FLOAT), ("n", T.INTEGER)]
    a = analyze("def f(img: Image) -> tuple[Image, int]:\n    return img, 3\n")
    assert outputs(a) == [("result_1", T.IMAGE), ("result_2", T.INTEGER)]
    a = analyze("def f(img: Image) -> tuple[Image, int]:\n    x = y = 1\n    return x, x\n")
    assert [n for n, _ in outputs(a)] == ["result_1", "result_2"]  # nombres repetidos: genéricos


def test_a_vector_return_is_one_output_not_two():
    a = analyze("def f(img: Image) -> tuple[float, float]:\n    return 1.0, 2.0\n")
    assert outputs(a) == [("result", T.VECTOR2)]
    a = analyze("def f(img: Image) -> tuple[float, float, float]:\n    return 1.0, 2.0, 3.0\n")
    assert outputs(a) == [("result", T.VECTOR3)]
    a = analyze("def f(img: Image) -> tuple[tuple[float, float], int]:\n    return (1.0, 2.0), 3\n")
    assert outputs(a) == [("result_1", T.VECTOR2), ("result_2", T.INTEGER)]  # vector + entero


def test_functions_without_return_annotation():
    a = analyze("def f(x: int):\n    return x * 2\n")
    assert outputs(a) == [("result", T.ANY)] and any(
        "sin anotación de retorno" in w.message for w in a.warnings
    )
    a = analyze("def f(x: int):\n    print(x)\n")
    assert outputs(a) == [] and not a.warnings
    a = analyze("def f(x: int) -> None:\n    print(x)\n")
    assert outputs(a) == [] and not a.warnings
    a = analyze("def f(x: int) -> None:\n    return x\n")
    assert outputs(a) == [] and any("declara `-> None`" in w.message for w in a.warnings)


def test_nested_functions_do_not_count_as_returns():
    a = analyze("def f(x: int):\n    def ayuda():\n        return 1\n    print(x)\n")
    assert outputs(a) == []


@pytest.mark.parametrize(
    "returns,expected",
    [
        ("int", T.INTEGER),
        ("str", T.STRING),
        ("Color", T.COLOR),
        ("Literal['a', 'b']", T.STRING),
        ("Any", T.ANY),
    ],
)
def test_return_types(returns, expected):
    a = analyze(f"def f(x: int) -> {returns}:\n    return x\n")
    assert a.ok and outputs(a) == [("x", expected)]


def test_unsupported_return_type_is_an_error():
    a = analyze("def f(x: int) -> list:\n    return [x]\n")
    assert not a.ok and "tipo de retorno" in a.errors[0].message


def test_description_is_the_first_docstring_line():
    a = analyze('def f(x: int):\n    """Primera línea.\n\n    Más detalles.\n    """\n')
    assert a.description == "Primera línea."
    assert analyze("def f(x: int):\n    pass\n").description == ""


def test_every_template_is_valid():
    from palantir_nodes.ui.custom_nodes_dialog import TEMPLATES

    for name, code in TEMPLATES.items():
        a = analyze(code)
        assert a.ok and not a.warnings, (name, a.errors, a.warnings)
