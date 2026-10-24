"""Nodos matemáticos."""

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.categories import MATH
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec


@register_node
class Add(NodeDefinition):
    type_id = "math.add"
    label = "Add"
    category = MATH
    description = "A + B"
    inputs = (InputSpec("a", T.FLOAT, "A", default=0.0), InputSpec("b", T.FLOAT, "B", default=0.0))
    outputs = (OutputSpec("result", T.FLOAT, "Resultado"),)


@register_node
class Multiply(NodeDefinition):
    type_id = "math.multiply"
    label = "Multiply"
    category = MATH
    description = "A × B"
    inputs = (InputSpec("a", T.FLOAT, "A", default=1.0), InputSpec("b", T.FLOAT, "B", default=1.0))
    outputs = (OutputSpec("result", T.FLOAT, "Resultado"),)


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
    outputs = (OutputSpec("result", T.FLOAT, "Resultado"),)


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
    outputs = (OutputSpec("result", T.FLOAT, "Resultado"),)
