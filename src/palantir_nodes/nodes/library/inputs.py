"""Nodos de entrada."""

import os

import cv2
import numpy as np

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.categories import INPUT
from palantir_nodes.nodes.library._cv import to_uint8
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import OutputSpec, ParamKind, ParamSpec

IMAGE_FILTER = "Imágenes (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;Todos (*)"

_READ_FLAGS = {
    "color": cv2.IMREAD_COLOR,
    "grayscale": cv2.IMREAD_GRAYSCALE,
    "unchanged": cv2.IMREAD_UNCHANGED,
}


def read_image(path: str, mode: str = "color") -> np.ndarray:
    """Lee una imagen (rutas con tildes incluidas) o lanza ``ValueError`` explicativo."""
    if not path:
        raise ValueError("No se ha seleccionado ningún archivo de imagen")
    if not os.path.isfile(path):
        raise ValueError(f"No existe el archivo: {path}")
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError as exc:
        raise ValueError(f"No se pudo leer el archivo: {exc}") from exc
    img = cv2.imdecode(data, _READ_FLAGS[mode]) if data.size else None
    if img is None or img.size == 0:
        raise ValueError(f"El archivo no es una imagen válida: {os.path.basename(path)}")
    return to_uint8(img)


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

    @classmethod
    def cache_key_extra(cls, params):
        try:
            stat = os.stat(params["path"])
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def process(self, ctx, inputs, params):
        img = read_image(params["path"], params["mode"])
        return {"image": img, "width": img.shape[1], "height": img.shape[0]}


@register_node
class Number(NodeDefinition):
    type_id = "input.number"
    label = "Number"
    category = INPUT
    description = "Valor numérico decimal."
    outputs = (OutputSpec("value", T.FLOAT),)
    params = (ParamSpec("value", ParamKind.FLOAT, 0.5, label="Valor"),)

    def process(self, ctx, inputs, params):
        return {"value": params["value"]}


@register_node
class Integer(NodeDefinition):
    type_id = "input.integer"
    label = "Integer"
    category = INPUT
    description = "Valor numérico entero."
    outputs = (OutputSpec("value", T.INTEGER),)
    params = (ParamSpec("value", ParamKind.INT, 1, label="Valor"),)

    def process(self, ctx, inputs, params):
        return {"value": params["value"]}


@register_node
class BooleanValue(NodeDefinition):
    type_id = "input.boolean"
    label = "Boolean"
    category = INPUT
    description = "Valor verdadero o falso."
    outputs = (OutputSpec("value", T.BOOLEAN),)
    params = (ParamSpec("value", ParamKind.BOOL, True, label="Valor"),)

    def process(self, ctx, inputs, params):
        return {"value": params["value"]}


@register_node
class ColorValue(NodeDefinition):
    type_id = "input.color"
    label = "Color"
    category = INPUT
    description = "Color RGB."
    outputs = (OutputSpec("color", T.COLOR),)
    params = (ParamSpec("color", ParamKind.COLOR, (255, 255, 255), label="Color"),)

    def process(self, ctx, inputs, params):
        return {"color": params["color"]}
