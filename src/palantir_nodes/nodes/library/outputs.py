"""Nodos de salida."""

import os

import cv2

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import OUTPUT
from palantir_nodes.nodes.library._cv import image_in
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, ParamKind, ParamSpec


@register_node
class ImageViewer(NodeDefinition):
    type_id = "output.image_viewer"
    label = "Image Viewer"
    category = OUTPUT
    description = "Muestra la imagen en el visor de resultados."
    inputs = (InputSpec("image", T.IMAGE),)

    def process(self, ctx, inputs, params):
        image_in(inputs["image"])  # valida; el visor lee la entrada desde el resultado
        return {}

    def generate_code(self, gen, inputs, params):
        gen.uses_display = True
        title = gen.window_name("Image Viewer")
        lines = ["if show:", f"    cv2.imshow({title!r}, {inputs['image']})"]
        return CodeFragment(lines, {})


@register_node
class SaveImage(NodeDefinition):
    type_id = "output.save_image"
    label = "Save Image"
    category = OUTPUT
    description = "Guarda la imagen en disco al pulsar Ejecutar (no en la ejecución automática)."
    cacheable = False
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

    def process(self, ctx, inputs, params):
        img = image_in(inputs["image"])
        if not ctx.side_effects:
            return {}
        path = params["path"]
        if not path:
            raise ValueError("No se ha indicado el archivo de destino")
        ext = os.path.splitext(path)[1].lower()
        if not ext:
            raise ValueError("El archivo de destino necesita extensión (.png, .jpg…)")
        try:
            ok, buffer = cv2.imencode(ext, img)
        except cv2.error as exc:
            raise ValueError(f"Formato no soportado: {ext}") from exc
        if not ok:
            raise ValueError(f"No se pudo codificar la imagen como {ext}")
        try:
            buffer.tofile(path)
        except OSError as exc:
            raise ValueError(f"No se pudo escribir '{path}': {exc.strerror or exc}") from exc
        return {}

    def generate_code(self, gen, inputs, params):
        gen.helper("save_image")
        return CodeFragment([f"save_image({inputs['image']}, {params['path']!r})"], {})

    @classmethod
    def export_problems(cls, params):
        if not params["path"]:
            return ["no se ha indicado el archivo de destino"]
        if not os.path.splitext(params["path"])[1]:
            return ["el archivo de destino necesita extensión (.png, .jpg…)"]
        return []
