import pytest

from palantir_nodes.core.errors import ParamValidationError
from palantir_nodes.core.types import SocketType as T
from palantir_nodes.core.types import conversion_between, is_compatible
from palantir_nodes.nodes.specs import InputSpec, ParamKind, ParamSpec


@pytest.mark.parametrize("t", list(T))
def test_same_type_is_compatible(t):
    assert is_compatible(t, t)
    assert conversion_between(t, t) is None


@pytest.mark.parametrize("t", list(T))
def test_any_input_accepts_everything(t):
    assert is_compatible(t, T.ANY)


def test_any_output_only_connects_to_any():
    assert not is_compatible(T.ANY, T.IMAGE)
    assert not is_compatible(T.ANY, T.FLOAT)


@pytest.mark.parametrize(
    "src,dst",
    [(T.INTEGER, T.FLOAT), (T.FLOAT, T.INTEGER), (T.BOOLEAN, T.FLOAT), (T.COLOR, T.VECTOR3)],
)
def test_explicit_conversions(src, dst):
    assert is_compatible(src, dst)
    assert conversion_between(src, dst) is not None


@pytest.mark.parametrize(
    "src,dst", [(T.IMAGE, T.FLOAT), (T.STRING, T.FLOAT), (T.FLOAT, T.IMAGE), (T.VIDEO, T.IMAGE)]
)
def test_incompatible_types(src, dst):
    assert not is_compatible(src, dst)


def test_conversion_functions():
    assert conversion_between(T.FLOAT, T.INTEGER).convert(2.6) == 3
    assert conversion_between(T.VECTOR3, T.COLOR).convert((300.0, -4.0, 10.4)) == (255, 0, 10)


def test_int_param_clamps_and_rounds():
    spec = ParamSpec("k", ParamKind.INT, 3, minimum=1, maximum=9)
    assert spec.coerce(20) == 9
    assert spec.coerce(0) == 1
    assert spec.coerce(4.6) == 5


def test_enum_rejects_unknown_option():
    spec = ParamSpec("m", ParamKind.ENUM, "a", options=(("a", "A"),))
    with pytest.raises(ParamValidationError):
        spec.coerce("z")


def test_color_and_vector_coercion():
    color = ParamSpec("c", ParamKind.COLOR, (0, 0, 0))
    assert color.coerce([10, 300, -1]) == (10, 255, 0)
    vec = ParamSpec("v", ParamKind.VECTOR2, (0, 0))
    assert vec.coerce([1, 2]) == (1.0, 2.0)
    with pytest.raises(ParamValidationError):
        vec.coerce([1, 2, 3])


def test_invalid_number_raises_validation_error():
    with pytest.raises(ParamValidationError):
        ParamSpec("f", ParamKind.FLOAT, 0.0).coerce("abc")


def test_image_input_cannot_have_default():
    with pytest.raises(ValueError):
        InputSpec("image", T.IMAGE, default=0)
