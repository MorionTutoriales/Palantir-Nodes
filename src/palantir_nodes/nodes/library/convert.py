"""Conversión entre tipos de valor: números, enteros y texto."""

import math

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import CONVERSION
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec


def parse_number(text: str) -> float:
    """Número escrito en texto; acepta la coma decimal. Lanza ``ValueError`` si no lo es."""
    value = float(str(text).strip().replace(",", "."))
    if not math.isfinite(value):
        raise ValueError("no es un número finito")
    return value


@register_node
class NumberToString(NodeDefinition):
    type_id = "convert.number_to_string"
    label = "Number to String"
    category = CONVERSION
    description = "Convierte un número en texto con los decimales indicados."
    inputs = (InputSpec("value", T.FLOAT, "Número", default=0.0),)
    outputs = (OutputSpec("text", T.STRING, "Texto"),)
    params = (
        ParamSpec(
            "decimals",
            ParamKind.INT,
            2,
            label="Decimales",
            minimum=0,
            maximum=12,
            connectable=False,
        ),
    )

    def process(self, ctx, inputs, params):
        return {"text": f"{inputs['value']:.{params['decimals']}f}"}

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("text")
        return CodeFragment([f'{o} = f"{{{inputs["value"]}:.{params["decimals"]}f}}"'], {"text": o})


@register_node
class StringToNumber(NodeDefinition):
    type_id = "convert.string_to_number"
    label = "String to Number"
    category = CONVERSION
    description = (
        "Convierte un texto en número (acepta coma decimal). Si no es un número, falla o usa "
        "el valor por defecto, según «Si no es válido»."
    )
    inputs = (InputSpec("text", T.STRING, "Texto", default="0"),)
    outputs = (
        OutputSpec("value", T.FLOAT, "Número"),
        OutputSpec("valid", T.BOOLEAN, "Válido"),
    )
    params = (
        ParamSpec(
            "on_error",
            ParamKind.ENUM,
            "default",
            label="Si no es válido",
            options=(("default", "Usar el valor por defecto"), ("error", "Mostrar un error")),
            connectable=False,
        ),
        ParamSpec("default", ParamKind.FLOAT, 0.0, label="Por defecto", connectable=False),
    )

    def process(self, ctx, inputs, params):
        try:
            return {"value": parse_number(inputs["text"]), "valid": True}
        except ValueError:
            if params["on_error"] == "error":
                raise ValueError(f"'{inputs['text']}' no es un número") from None
            return {"value": params["default"], "valid": False}

    def generate_code(self, gen, inputs, params):
        gen.helper("parse_number")
        value, valid = gen.new_var("number"), gen.new_var("valid")
        text = inputs["text"]
        lines = [
            "try:",
            f"    {value}, {valid} = parse_number({text}), True",
            "except ValueError:",
        ]
        if params["on_error"] == "error":
            lines.append(f"    raise ValueError(f\"'{{{text}}}' no es un número\") from None")
        else:
            lines.append(f"    {value}, {valid} = {params['default']!r}, False")
        return CodeFragment(lines, {"value": value, "valid": valid})


@register_node
class IntegerToFloat(NodeDefinition):
    type_id = "convert.integer_to_float"
    label = "Integer to Float"
    category = CONVERSION
    description = "Convierte un entero en un número decimal."
    inputs = (InputSpec("value", T.INTEGER, "Entero", default=0),)
    outputs = (OutputSpec("value", T.FLOAT, "Decimal"),)

    def process(self, ctx, inputs, params):
        return {"value": float(inputs["value"])}

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("decimal")
        return CodeFragment([f"{o} = float({inputs['value']})"], {"value": o})


_ROUNDING = {
    "floor": ("Piso (hacia abajo)", math.floor, "math.floor"),
    "ceil": ("Techo (hacia arriba)", math.ceil, "math.ceil"),
    "round": ("Redondear", round, "round"),
    "trunc": ("Truncar (hacia cero)", math.trunc, "math.trunc"),
}


@register_node
class FloatToInteger(NodeDefinition):
    type_id = "convert.float_to_integer"
    label = "Float to Integer"
    category = CONVERSION
    description = "Convierte un decimal en entero: piso, techo, redondeo o truncado."
    inputs = (InputSpec("value", T.FLOAT, "Decimal", default=0.0),)
    outputs = (OutputSpec("value", T.INTEGER, "Entero"),)
    params = (
        ParamSpec(
            "mode",
            ParamKind.ENUM,
            "floor",
            label="Modo",
            options=tuple((key, label) for key, (label, _fn, _code) in _ROUNDING.items()),
            connectable=False,
        ),
    )

    def process(self, ctx, inputs, params):
        return {"value": int(_ROUNDING[params["mode"]][1](inputs["value"]))}

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("integer")
        function = _ROUNDING[params["mode"]][2]
        return CodeFragment([f"{o} = int({function}({inputs['value']}))"], {"value": o})
