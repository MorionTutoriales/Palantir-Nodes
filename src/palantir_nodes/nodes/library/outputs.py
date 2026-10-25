"""Nodos de salida."""

import os

import cv2

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.media.capture import open_video_writer
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import OUTPUT
from palantir_nodes.nodes.library._cv import as_bgr, image_in
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
class StringViewer(NodeDefinition):
    type_id = "output.string_viewer"
    label = "String Viewer"
    category = OUTPUT
    description = (
        "Muestra un texto dentro del nodo. Al seleccionarlo (o fijar el visor en él) el texto "
        "completo se lee en el visor de resultados; el script exportado lo imprime en la consola."
    )
    shows_text = "text"
    inputs = (InputSpec("text", T.STRING, "Texto"),)

    def process(self, ctx, inputs, params):
        return {}

    def generate_code(self, gen, inputs, params):
        last = gen.new_var("last_text")
        text = inputs["text"]
        lines = [
            f"if {text} != {last}:",
            f"    print({text})",
            f"    {last} = {text}",
        ]
        return CodeFragment(lines, {}, pre=[f"{last} = None"])


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


@register_node
class VideoViewer(NodeDefinition):
    type_id = "output.video_viewer"
    label = "Video Viewer"
    category = OUTPUT
    description = (
        "Muestra los fotogramas en el visor (con FPS) durante la ejecución en tiempo real."
    )
    inputs = (InputSpec("image", T.IMAGE, "Fotograma"),)

    def process(self, ctx, inputs, params):
        image_in(inputs["image"])
        return {}

    def generate_code(self, gen, inputs, params):
        gen.uses_display = True
        title = gen.window_name("Video Viewer")
        return CodeFragment(["if show:", f"    cv2.imshow({title!r}, {inputs['image']})"], {})


VIDEO_CODECS = (("mp4v", "MP4 (mp4v)"), ("MJPG", "Motion JPEG (MJPG)"), ("XVID", "XVID"))


@register_node
class SaveVideo(NodeDefinition):
    type_id = "output.save_video"
    label = "Save Video"
    category = OUTPUT
    description = "Escribe los fotogramas en un archivo de video (solo en tiempo real con F5)."
    cacheable = False
    inputs = (InputSpec("image", T.IMAGE, "Fotograma"),)
    params = (
        ParamSpec(
            "path",
            ParamKind.FILE_PATH,
            "",
            label="Archivo",
            save_dialog=True,
            file_filter="Video (*.mp4 *.avi);;Todos (*)",
        ),
        ParamSpec(
            "fps", ParamKind.FLOAT, 30.0, label="FPS", minimum=1.0, maximum=240.0, connectable=False
        ),
        ParamSpec("codec", ParamKind.ENUM, "mp4v", label="Códec", options=VIDEO_CODECS),
    )

    def process(self, ctx, inputs, params):
        img = as_bgr(image_in(inputs["image"]))
        if not (ctx.realtime and ctx.side_effects):
            return {}  # solo escribe durante una ejecución en tiempo real iniciada con F5
        key = (params["path"], params["fps"], params["codec"], img.shape[:2])
        entry = ctx.resources.get(ctx.node_id)
        if entry is not None and entry[0][:3] != key[:3]:
            entry[2]()  # cambió el destino o el códec: se reinicia el archivo
            entry = None
        if entry is None:
            writer = open_video_writer(params["path"], params["fps"], params["codec"], img)
            entry = (key, writer, writer.release)
            ctx.resources[ctx.node_id] = entry
        if entry[0][3] != img.shape[:2]:
            raise ValueError("El tamaño del fotograma cambió; detén y reinicia la ejecución")
        entry[1].write(img)
        return {}

    def generate_code(self, gen, inputs, params):
        gen.helper("open_video_writer")
        gen.helper("as_bgr")
        writer, frame = gen.new_var("writer"), gen.new_var("frame_bgr")
        lines = [
            f"{frame} = as_bgr({inputs['image']})",
            f"if {writer} is None:",
            f"    {writer} = open_video_writer({params['path']!r}, {params['fps']!r}, "
            f"{params['codec']!r}, {frame})",
            f"{writer}.write({frame})",
        ]
        return CodeFragment(
            lines,
            {},
            pre=[f"{writer} = None"],
            cleanup=[f"if {writer} is not None:", f"    {writer}.release()"],
        )

    @classmethod
    def export_problems(cls, params):
        if not params["path"]:
            return ["no se ha indicado el archivo de video de destino"]
        if not os.path.splitext(params["path"])[1]:
            return ["el archivo de destino necesita extensión (.mp4, .avi)"]
        return []
