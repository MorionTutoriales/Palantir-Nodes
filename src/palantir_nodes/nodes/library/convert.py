"""Conversión entre tipos de valor: números, enteros y texto."""

import json
import math

import numpy as np

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


def to_json_text(value, compact=True, decimals=None):
    """Texto JSON de un valor de Python o NumPy (tuplas y arrays pasan a listas).

    ``decimals`` redondea los decimales; los NaN e infinitos pasan a ``null`` (JSON no los admite).
    """

    def plain(item):
        if isinstance(item, dict):
            return {str(key): plain(inner) for key, inner in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(inner) for inner in item]
        if isinstance(item, np.ndarray):
            return plain(item.tolist())
        if isinstance(item, (bool, np.bool_)):
            return bool(item)
        if isinstance(item, (int, np.integer)):
            return int(item)
        if isinstance(item, (float, np.floating)):
            number = float(item)
            if not math.isfinite(number):
                return None
            return number if decimals is None else round(number, decimals)
        if item is None or isinstance(item, str):
            return item
        raise ValueError(f"No se puede convertir a JSON un valor de tipo {type(item).__name__}")

    separators = (",", ":") if compact else None
    return json.dumps(
        plain(value), ensure_ascii=False, separators=separators, indent=None if compact else 2
    )


def json_value(text, path=""):
    """Valor que hay en ``path`` dentro de un texto JSON: ``(número, texto, encontrado)``.

    ``path`` son pasos separados por puntos: posiciones en listas (``0``, ``-1``) o nombres de
    claves (``manos.0.points.8.0``). Vacío = todo el JSON.
    """
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return 0.0, "", False
    for part in [step for step in str(path).split(".") if step != ""]:
        try:
            if isinstance(value, list):
                value = value[int(part)]
            elif isinstance(value, dict):
                value = value[part]
            else:
                return 0.0, "", False
        except (KeyError, IndexError, ValueError):
            return 0.0, "", False
    number = float(value) if isinstance(value, (bool, int, float)) else 0.0
    shown = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )
    return number, shown, True


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


_DECIMALS = ParamSpec(
    "decimals", ParamKind.INT, 3, label="Decimales", minimum=0, maximum=8, connectable=False
)
_COMPACT = ParamSpec(
    "compact",
    ParamKind.BOOL,
    True,
    label="Compacto",
    connectable=False,
    tooltip="Una sola línea sin espacios (si no, se escribe con sangría y varias líneas)",
)


@register_node
class ValueToJson(NodeDefinition):
    type_id = "convert.to_json"
    label = "Value to JSON"
    category = CONVERSION
    description = (
        "Convierte un valor (número, vector, color, lista de puntos…) en texto JSON, listo para "
        "mostrarlo en un String Viewer o enviarlo por la red."
    )
    inputs = (InputSpec("value", T.ANY, "Valor"),)
    outputs = (OutputSpec("json", T.STRING, "JSON"),)
    params = (_DECIMALS, _COMPACT)

    def process(self, ctx, inputs, params):
        return {"json": to_json_text(inputs["value"], params["compact"], params["decimals"])}

    def generate_code(self, gen, inputs, params):
        gen.helper("to_json_text")
        o = gen.new_var("json_text")
        call = f"to_json_text({inputs['value']}, {params['compact']!r}, {params['decimals']!r})"
        return CodeFragment([f"{o} = {call}"], {"json": o})


@register_node
class JsonValue(NodeDefinition):
    type_id = "convert.json_value"
    label = "JSON Value"
    category = CONVERSION
    description = (
        "Saca un valor de un texto JSON siguiendo un camino de pasos separados por puntos "
        "(posición en listas o nombre de clave), p. ej. «0.points.8.0». Si no existe o el "
        "texto no es JSON, «Encontrado» es falso."
    )
    inputs = (InputSpec("json", T.STRING, "JSON", default=""),)
    outputs = (
        OutputSpec("number", T.FLOAT, "Número"),
        OutputSpec("text", T.STRING, "Texto"),
        OutputSpec("found", T.BOOLEAN, "Encontrado"),
    )
    params = (
        ParamSpec(
            "path",
            ParamKind.STRING,
            "",
            label="Camino",
            connectable=False,
            tooltip="Ejemplo: 0.points.8.0 (vacío = todo). Negativos: desde el final.",
        ),
    )

    def process(self, ctx, inputs, params):
        number, text, found = json_value(inputs["json"], params["path"])
        return {"number": number, "text": text, "found": found}

    def generate_code(self, gen, inputs, params):
        gen.helper("json_value")
        number, text, found = (gen.new_var(n) for n in ("json_number", "json_text", "json_found"))
        line = f"{number}, {text}, {found} = json_value({inputs['json']}, {params['path']!r})"
        return CodeFragment([line], {"number": number, "text": text, "found": found})
