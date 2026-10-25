"""Conversión de espacios de color: de imágenes y de valores de color."""

import cv2

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import CONVERSION
from palantir_nodes.nodes.library._cv import as_bgr, hsv_to_rgb, image_in, rgb_to_hsv
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec

# Espacio -> (constante de OpenCV desde BGR, constante hacia BGR). BGR no necesita conversión.
_SPACES = {
    "rgb": ("COLOR_BGR2RGB", "COLOR_RGB2BGR"),
    "hsv": ("COLOR_BGR2HSV", "COLOR_HSV2BGR"),
    "hls": ("COLOR_BGR2HLS", "COLOR_HLS2BGR"),
    "lab": ("COLOR_BGR2LAB", "COLOR_LAB2BGR"),
    "ycrcb": ("COLOR_BGR2YCrCb", "COLOR_YCrCb2BGR"),
    "gray": ("COLOR_BGR2GRAY", "COLOR_GRAY2BGR"),
}
_SPACE_OPTIONS = (
    ("bgr", "BGR"),
    ("rgb", "RGB"),
    ("hsv", "HSV"),
    ("hls", "HLS"),
    ("lab", "Lab"),
    ("ycrcb", "YCrCb"),
    ("gray", "Gris"),
)


def _steps(source: str, target: str) -> list[str]:
    """Constantes de ``cv2`` que se aplican en orden (pasando por BGR)."""
    if source == target:
        return []
    steps = []
    if source != "bgr":
        steps.append(_SPACES[source][1])
    if target != "bgr":
        steps.append(_SPACES[target][0])
    return steps


@register_node
class ConvertColor(NodeDefinition):
    type_id = "image.convert_color"
    label = "Convert Color Space"
    category = CONVERSION
    description = (
        "Convierte una imagen entre BGR, RGB, HSV, HLS, Lab, YCrCb y gris. En HSV: H 0-179, "
        "S y V 0-255. Indica en qué espacio está la imagen de entrada (origen)."
    )
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec("source", ParamKind.ENUM, "bgr", label="Origen", options=_SPACE_OPTIONS),
        ParamSpec("target", ParamKind.ENUM, "hsv", label="Destino", options=_SPACE_OPTIONS),
    )

    def process(self, ctx, inputs, params):
        img = image_in(inputs["image"])
        source, target = params["source"], params["target"]
        if source == "gray":
            img = img if img.ndim == 2 else cv2.cvtColor(as_bgr(img), cv2.COLOR_BGR2GRAY)
        elif source == "bgr":
            img = as_bgr(img)
        elif img.ndim != 3 or img.shape[2] != 3:
            raise ValueError(f"El origen {source.upper()} necesita una imagen de 3 canales")
        for name in _steps(source, target):
            img = cv2.cvtColor(img, getattr(cv2, name))
        return {"image": img}

    def generate_code(self, gen, inputs, params):
        src, o = inputs["image"], gen.new_var("converted")
        source, target = params["source"], params["target"]
        if source in ("gray", "bgr"):
            gen.helper("as_bgr")
        if source == "gray":
            lines = [
                f"{o} = {src} if {src}.ndim == 2 else cv2.cvtColor(as_bgr({src}), "
                "cv2.COLOR_BGR2GRAY)"
            ]
        elif source == "bgr":
            lines = [f"{o} = as_bgr({src})"]
        else:
            message = f"El origen {source.upper()} necesita una imagen de 3 canales"
            lines = [
                f"if {src}.ndim != 3 or {src}.shape[2] != 3:",
                f"    raise ValueError({message!r})",
                f"{o} = {src}",
            ]
        lines += [f"{o} = cv2.cvtColor({o}, cv2.{name})" for name in _steps(source, target)]
        return CodeFragment(lines, {"image": o})


@register_node
class RgbToHsv(NodeDefinition):
    type_id = "color.rgb_to_hsv"
    label = "RGB to HSV"
    category = CONVERSION
    description = "Convierte un color RGB en HSV de OpenCV (H 0-179, S y V 0-255)."
    inputs = (InputSpec("color", T.COLOR, "Color", default=(255, 0, 0)),)
    outputs = (OutputSpec("hsv", T.VECTOR3, "HSV"),)

    def process(self, ctx, inputs, params):
        return {"hsv": rgb_to_hsv(inputs["color"])}

    def generate_code(self, gen, inputs, params):
        gen.helper("rgb_to_hsv")
        o = gen.new_var("hsv")
        return CodeFragment([f"{o} = rgb_to_hsv({inputs['color']})"], {"hsv": o})


@register_node
class HsvToRgb(NodeDefinition):
    type_id = "color.hsv_to_rgb"
    label = "HSV to RGB"
    category = CONVERSION
    description = "Convierte un HSV de OpenCV (H 0-179, S y V 0-255) en un color RGB."
    inputs = (InputSpec("hsv", T.VECTOR3, "HSV", default=(0.0, 255.0, 255.0)),)
    outputs = (OutputSpec("color", T.COLOR, "Color"),)

    def process(self, ctx, inputs, params):
        return {"color": hsv_to_rgb(inputs["hsv"])}

    def generate_code(self, gen, inputs, params):
        gen.helper("hsv_to_rgb")
        o = gen.new_var("color_rgb")
        return CodeFragment([f"{o} = hsv_to_rgb({inputs['hsv']})"], {"color": o})
