"""Nodos de composición."""

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.categories import COMPOSITE
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec


@register_node
class BlendImages(NodeDefinition):
    type_id = "compose.blend"
    label = "Blend Images"
    category = COMPOSITE
    description = "Mezcla dos imágenes."
    inputs = (
        InputSpec("factor", T.FLOAT, "Factor", default=0.5, minimum=0.0, maximum=1.0),
        InputSpec("image_a", T.IMAGE, "Imagen A"),
        InputSpec("image_b", T.IMAGE, "Imagen B"),
    )
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "mode",
            ParamKind.ENUM,
            "mix",
            label="Modo",
            options=(
                ("mix", "Mezcla"),
                ("add", "Suma"),
                ("multiply", "Multiplicar"),
                ("screen", "Trama"),
            ),
        ),
    )


@register_node
class BitwiseNot(NodeDefinition):
    type_id = "compose.bitwise_not"
    label = "Bitwise NOT"
    category = COMPOSITE
    description = "Invierte los bits de la imagen."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
