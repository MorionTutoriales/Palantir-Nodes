"""Nodos de entrada."""

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.categories import INPUT
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import OutputSpec, ParamKind, ParamSpec

IMAGE_FILTER = "Imágenes (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;Todos (*)"


@register_node
class LoadImage(NodeDefinition):
    type_id = "input.load_image"
    label = "Load Image"
    category = INPUT
    description = "Carga una imagen desde disco."
    outputs = (
        OutputSpec("image", T.IMAGE),
        OutputSpec("width", T.INTEGER),
        OutputSpec("height", T.INTEGER),
    )
    params = (
        ParamSpec("path", ParamKind.FILE_PATH, "", label="Archivo", file_filter=IMAGE_FILTER),
        ParamSpec(
            "mode",
            ParamKind.ENUM,
            "color",
            label="Modo",
            options=(
                ("color", "Color (BGR)"),
                ("grayscale", "Escala de grises"),
                ("unchanged", "Sin cambios (alfa)"),
            ),
        ),
    )


@register_node
class Number(NodeDefinition):
    type_id = "input.number"
    label = "Number"
    category = INPUT
    description = "Valor numérico decimal."
    outputs = (OutputSpec("value", T.FLOAT),)
    params = (ParamSpec("value", ParamKind.FLOAT, 0.5, label="Valor"),)


@register_node
class Integer(NodeDefinition):
    type_id = "input.integer"
    label = "Integer"
    category = INPUT
    description = "Valor numérico entero."
    outputs = (OutputSpec("value", T.INTEGER),)
    params = (ParamSpec("value", ParamKind.INT, 1, label="Valor"),)


@register_node
class BooleanValue(NodeDefinition):
    type_id = "input.boolean"
    label = "Boolean"
    category = INPUT
    description = "Valor verdadero o falso."
    outputs = (OutputSpec("value", T.BOOLEAN),)
    params = (ParamSpec("value", ParamKind.BOOL, True, label="Valor"),)


@register_node
class ColorValue(NodeDefinition):
    type_id = "input.color"
    label = "Color"
    category = INPUT
    description = "Color RGB."
    outputs = (OutputSpec("color", T.COLOR),)
    params = (ParamSpec("color", ParamKind.COLOR, (255, 255, 255), label="Color"),)
