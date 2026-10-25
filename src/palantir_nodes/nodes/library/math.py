"""Nodos matemáticos."""

import math
import operator

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import CodeFragment, Expr, NodeDefinition
from palantir_nodes.nodes.categories import MATH
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec


def _ab(default_a: float = 0.0, default_b: float = 0.0) -> tuple[InputSpec, InputSpec]:
    return (
        InputSpec("a", T.FLOAT, "A", default=default_a),
        InputSpec("b", T.FLOAT, "B", default=default_b),
    )


_RESULT = (OutputSpec("result", T.FLOAT, "Resultado"),)


@register_node
class Add(NodeDefinition):
    type_id = "math.add"
    label = "Add"
    category = MATH
    description = "A + B"
    inputs = _ab()
    outputs = _RESULT

    def process(self, ctx, inputs, params):
        return {"result": inputs["a"] + inputs["b"]}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("total")
        a, b = inputs["a"], inputs["b"]
        return CodeFragment([f"{r} = {a} + {b}"], {"result": r})


@register_node
class Subtract(NodeDefinition):
    type_id = "math.subtract"
    label = "Subtract"
    category = MATH
    description = "A − B"
    inputs = _ab()
    outputs = _RESULT

    def process(self, ctx, inputs, params):
        return {"result": inputs["a"] - inputs["b"]}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("difference")
        a, b = inputs["a"], inputs["b"]
        return CodeFragment([f"{r} = {a} - {b}"], {"result": r})


@register_node
class Multiply(NodeDefinition):
    type_id = "math.multiply"
    label = "Multiply"
    category = MATH
    description = "A × B"
    inputs = _ab(1.0, 1.0)
    outputs = _RESULT

    def process(self, ctx, inputs, params):
        return {"result": inputs["a"] * inputs["b"]}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("product")
        a, b = inputs["a"], inputs["b"]
        return CodeFragment([f"{r} = {a} * {b}"], {"result": r})


@register_node
class Divide(NodeDefinition):
    type_id = "math.divide"
    label = "Divide"
    category = MATH
    description = "A ÷ B"
    inputs = _ab(1.0, 1.0)
    outputs = _RESULT

    def process(self, ctx, inputs, params):
        if inputs["b"] == 0:
            raise ValueError("División entre cero")
        return {"result": inputs["a"] / inputs["b"]}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("quotient")
        a, b = inputs["a"], inputs["b"]
        lines = [
            f"if {b} == 0:",
            '    raise ValueError("División entre cero")',
            f"{r} = {a} / {b}",
        ]
        return CodeFragment(lines, {"result": r})


@register_node
class Clamp(NodeDefinition):
    type_id = "math.clamp"
    label = "Clamp"
    category = MATH
    description = "Limita un valor al rango [mín, máx]."
    inputs = (
        InputSpec("value", T.FLOAT, "Valor", default=0.5),
        InputSpec("min", T.FLOAT, "Mín", default=0.0),
        InputSpec("max", T.FLOAT, "Máx", default=1.0),
    )
    outputs = _RESULT

    def process(self, ctx, inputs, params):
        low, high = inputs["min"], inputs["max"]
        if low > high:
            raise ValueError(f"El mínimo ({low}) es mayor que el máximo ({high})")
        return {"result": min(max(inputs["value"], low), high)}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("clamped")
        v, lo, hi = inputs["value"], inputs["min"], inputs["max"]
        lines = [
            f"if {lo} > {hi}:",
            f'    raise ValueError(f"El mínimo ({{{lo}}}) es mayor que el máximo ({{{hi}}})")',
            f"{r} = min(max({v}, {lo}), {hi})",
        ]
        return CodeFragment(lines, {"result": r})


@register_node
class MapRange(NodeDefinition):
    type_id = "math.map_range"
    label = "Map Range"
    category = MATH
    description = "Reasigna un valor de un rango a otro."
    inputs = (
        InputSpec("value", T.FLOAT, "Valor", default=0.5),
        InputSpec("from_min", T.FLOAT, "Desde mín", default=0.0),
        InputSpec("from_max", T.FLOAT, "Desde máx", default=1.0),
        InputSpec("to_min", T.FLOAT, "Hacia mín", default=0.0),
        InputSpec("to_max", T.FLOAT, "Hacia máx", default=255.0),
    )
    outputs = _RESULT
    params = (ParamSpec("clamp", ParamKind.BOOL, False, label="Limitar al rango"),)

    def process(self, ctx, inputs, params):
        span = inputs["from_max"] - inputs["from_min"]
        if span == 0:
            raise ValueError("El rango de origen tiene longitud cero")
        t = (inputs["value"] - inputs["from_min"]) / span
        if params["clamp"]:
            t = min(max(t, 0.0), 1.0)
        return {"result": inputs["to_min"] + t * (inputs["to_max"] - inputs["to_min"])}

    def generate_code(self, gen, inputs, params):
        r, span, t = gen.new_var("mapped"), gen.new_var("span"), gen.new_var("fraction")
        v, fmin, fmax = inputs["value"], inputs["from_min"], inputs["from_max"]
        tmin, tmax = inputs["to_min"], inputs["to_max"]
        lines = [
            f"{span} = {fmax} - {fmin}",
            f"if {span} == 0:",
            '    raise ValueError("El rango de origen tiene longitud cero")',
            f"{t} = ({v} - {fmin}) / {span}",
        ]
        clamp = params["clamp"]
        limit = f"{t} = min(max({t}, 0.0), 1.0)"
        if isinstance(clamp, Expr):  # se decide al ejecutar el script
            lines += [f"if {clamp}:", f"    {limit}"]
        elif clamp:
            lines.append(limit)
        lines.append(f"{r} = {tmin} + {t} * ({tmax} - {tmin})")
        return CodeFragment(lines, {"result": r})


@register_node
class Minimum(NodeDefinition):
    type_id = "math.minimum"
    label = "Minimum"
    category = MATH
    description = "El menor de A y B."
    inputs = _ab()
    outputs = _RESULT

    def process(self, ctx, inputs, params):
        return {"result": min(inputs["a"], inputs["b"])}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("minimum")
        a, b = inputs["a"], inputs["b"]
        return CodeFragment([f"{r} = min({a}, {b})"], {"result": r})


@register_node
class Maximum(NodeDefinition):
    type_id = "math.maximum"
    label = "Maximum"
    category = MATH
    description = "El mayor de A y B."
    inputs = _ab()
    outputs = _RESULT

    def process(self, ctx, inputs, params):
        return {"result": max(inputs["a"], inputs["b"])}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("maximum")
        a, b = inputs["a"], inputs["b"]
        return CodeFragment([f"{r} = max({a}, {b})"], {"result": r})


_COMPARISONS = {
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
    "eq": operator.eq,
    "ne": operator.ne,
}


@register_node
class Compare(NodeDefinition):
    type_id = "math.compare"
    label = "Compare"
    category = MATH
    description = "Compara A con B."
    inputs = _ab()
    outputs = (OutputSpec("result", T.BOOLEAN, "Resultado"),)
    params = (
        ParamSpec(
            "op",
            ParamKind.ENUM,
            "gt",
            label="Operación",
            options=(
                ("gt", "A > B"),
                ("ge", "A ≥ B"),
                ("lt", "A < B"),
                ("le", "A ≤ B"),
                ("eq", "A = B"),
                ("ne", "A ≠ B"),
            ),
        ),
    )

    def process(self, ctx, inputs, params):
        return {"result": bool(_COMPARISONS[params["op"]](inputs["a"], inputs["b"]))}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var("comparison")
        symbol = {"gt": ">", "ge": ">=", "lt": "<", "le": "<=", "eq": "==", "ne": "!="}[
            params["op"]
        ]
        line = f"{r} = bool({inputs['a']} {symbol} {inputs['b']})"
        return CodeFragment([line], {"result": r})


_UNIT_OPTIONS = (("radians", "Radianes"), ("degrees", "Grados"))


class _Trig(NodeDefinition):
    """Base de seno y coseno: el ángulo entra en radianes o en grados."""

    category = MATH
    inputs = (InputSpec("angle", T.FLOAT, "Ángulo", default=0.0),)
    outputs = _RESULT
    params = (ParamSpec("unit", ParamKind.ENUM, "radians", label="Unidad", options=_UNIT_OPTIONS),)
    function_name = "sin"

    def process(self, ctx, inputs, params):
        angle = inputs["angle"]
        if params["unit"] == "degrees":
            angle = math.radians(angle)
        return {"result": float(getattr(math, self.function_name)(angle))}

    def generate_code(self, gen, inputs, params):
        r = gen.new_var(self.function_name)
        angle = inputs["angle"]
        if params["unit"] == "degrees":
            angle = f"math.radians({angle})"
        return CodeFragment([f"{r} = math.{self.function_name}({angle})"], {"result": r})


@register_node
class Sine(_Trig):
    type_id = "math.sin"
    label = "Sine"
    description = "Seno del ángulo (resultado entre -1 y 1)."
    function_name = "sin"


@register_node
class Cosine(_Trig):
    type_id = "math.cos"
    label = "Cosine"
    description = "Coseno del ángulo (resultado entre -1 y 1)."
    function_name = "cos"
