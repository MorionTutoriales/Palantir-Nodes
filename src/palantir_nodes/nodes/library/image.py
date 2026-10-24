"""Nodos de procesamiento de imágenes."""

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.categories import IMAGE
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec

INTERPOLATION = (
    ("linear", "Lineal"),
    ("nearest", "Vecino más cercano"),
    ("cubic", "Cúbica"),
    ("area", "Área"),
    ("lanczos", "Lanczos"),
)


@register_node
class Grayscale(NodeDefinition):
    type_id = "image.grayscale"
    label = "Grayscale"
    category = IMAGE
    description = "Convierte la imagen a escala de grises."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)


@register_node
class GaussianBlur(NodeDefinition):
    type_id = "image.gaussian_blur"
    label = "Gaussian Blur"
    category = IMAGE
    description = "Desenfoque gaussiano."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "ksize",
            ParamKind.INT,
            5,
            label="Kernel",
            minimum=1,
            maximum=99,
            step=2,
            slider=True,
            tooltip="Tamaño del kernel (se fuerza a impar).",
        ),
        ParamSpec(
            "sigma",
            ParamKind.FLOAT,
            0.0,
            label="Sigma",
            minimum=0.0,
            maximum=50.0,
            tooltip="0 = calculado a partir del kernel.",
        ),
    )


@register_node
class Threshold(NodeDefinition):
    type_id = "image.threshold"
    label = "Threshold"
    category = IMAGE
    description = "Umbral global."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE), OutputSpec("threshold", T.FLOAT, "Umbral usado"))
    params = (
        ParamSpec(
            "thresh",
            ParamKind.FLOAT,
            127.0,
            label="Umbral",
            minimum=0,
            maximum=255,
            slider=True,
            decimals=1,
        ),
        ParamSpec(
            "maxval", ParamKind.FLOAT, 255.0, label="Valor máx.", minimum=0, maximum=255, decimals=1
        ),
        ParamSpec(
            "method",
            ParamKind.ENUM,
            "binary",
            label="Método",
            options=(
                ("binary", "Binary"),
                ("binary_inv", "Binary Inv"),
                ("trunc", "Trunc"),
                ("tozero", "To Zero"),
                ("tozero_inv", "To Zero Inv"),
            ),
        ),
        ParamSpec("otsu", ParamKind.BOOL, False, label="Otsu"),
    )


@register_node
class Canny(NodeDefinition):
    type_id = "image.canny"
    label = "Canny Edge Detection"
    category = IMAGE
    description = "Detección de bordes de Canny."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("edges", T.IMAGE),)
    params = (
        ParamSpec(
            "threshold1",
            ParamKind.FLOAT,
            100.0,
            label="Umbral 1",
            minimum=0,
            maximum=1000,
            slider=True,
            decimals=1,
        ),
        ParamSpec(
            "threshold2",
            ParamKind.FLOAT,
            200.0,
            label="Umbral 2",
            minimum=0,
            maximum=1000,
            slider=True,
            decimals=1,
        ),
        ParamSpec(
            "aperture",
            ParamKind.ENUM,
            "3",
            label="Apertura",
            options=(("3", "3"), ("5", "5"), ("7", "7")),
        ),
        ParamSpec("l2_gradient", ParamKind.BOOL, False, label="Gradiente L2"),
    )


@register_node
class Resize(NodeDefinition):
    type_id = "image.resize"
    label = "Resize"
    category = IMAGE
    description = "Cambia el tamaño de la imagen por escala o a dimensiones fijas."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "mode",
            ParamKind.ENUM,
            "scale",
            label="Modo",
            options=(("scale", "Escala"), ("size", "Tamaño fijo")),
        ),
        ParamSpec("scale", ParamKind.FLOAT, 0.5, label="Escala", minimum=0.01, maximum=10.0),
        ParamSpec("width", ParamKind.INT, 640, label="Ancho", minimum=1, maximum=16384),
        ParamSpec("height", ParamKind.INT, 480, label="Alto", minimum=1, maximum=16384),
        ParamSpec(
            "interpolation", ParamKind.ENUM, "linear", label="Interpolación", options=INTERPOLATION
        ),
    )


@register_node
class Flip(NodeDefinition):
    type_id = "image.flip"
    label = "Flip"
    category = IMAGE
    description = "Voltea la imagen."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "axis",
            ParamKind.ENUM,
            "horizontal",
            label="Eje",
            options=(("horizontal", "Horizontal"), ("vertical", "Vertical"), ("both", "Ambos")),
        ),
    )
