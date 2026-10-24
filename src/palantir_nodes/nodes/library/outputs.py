"""Nodos de salida."""

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.categories import OUTPUT
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, ParamKind, ParamSpec


@register_node
class ImageViewer(NodeDefinition):
    type_id = "output.image_viewer"
    label = "Image Viewer"
    category = OUTPUT
    description = "Muestra la imagen en el visor de resultados."
    inputs = (InputSpec("image", T.IMAGE),)


@register_node
class SaveImage(NodeDefinition):
    type_id = "output.save_image"
    label = "Save Image"
    category = OUTPUT
    description = "Guarda la imagen en disco."
    inputs = (InputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "path",
            ParamKind.FILE_PATH,
            "",
            label="Archivo",
            save_dialog=True,
            file_filter="PNG (*.png);;JPEG (*.jpg *.jpeg);;Todos (*)",
        ),
    )
