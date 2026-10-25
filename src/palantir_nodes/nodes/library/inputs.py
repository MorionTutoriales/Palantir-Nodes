"""Nodos de entrada."""

import os

import cv2
import numpy as np

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.media.capture import (
    CaptureSource,
    open_camera_capture,
    open_video_capture,
)
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
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

    def generate_code(self, gen, inputs, params):
        gen.helper("read_image")
        img = gen.new_var("image")
        lines = [f"{img} = read_image({params['path']!r}, {params['mode']!r})"]
        outputs = {"image": img}
        if gen.wanted("width"):
            outputs["width"] = f"{img}.shape[1]"
        if gen.wanted("height"):
            outputs["height"] = f"{img}.shape[0]"
        return CodeFragment(lines, outputs)

    @classmethod
    def export_problems(cls, params):
        return [] if params["path"] else ["no se ha seleccionado ningún archivo de imagen"]


@register_node
class Number(NodeDefinition):
    type_id = "input.number"
    label = "Number"
    category = INPUT
    description = "Valor numérico decimal."
    outputs = (OutputSpec("value", T.FLOAT),)
    params = (ParamSpec("value", ParamKind.FLOAT, 0.5, label="Valor", connectable=False),)

    def process(self, ctx, inputs, params):
        return {"value": params["value"]}

    def generate_code(self, gen, inputs, params):
        v = gen.new_var("number")
        return CodeFragment([f"{v} = {params['value']!r}"], {"value": v})


@register_node
class Integer(NodeDefinition):
    type_id = "input.integer"
    label = "Integer"
    category = INPUT
    description = "Valor numérico entero."
    outputs = (OutputSpec("value", T.INTEGER),)
    params = (ParamSpec("value", ParamKind.INT, 1, label="Valor", connectable=False),)

    def process(self, ctx, inputs, params):
        return {"value": params["value"]}

    def generate_code(self, gen, inputs, params):
        v = gen.new_var("integer")
        return CodeFragment([f"{v} = {params['value']!r}"], {"value": v})


@register_node
class BooleanValue(NodeDefinition):
    type_id = "input.boolean"
    label = "Boolean"
    category = INPUT
    description = "Valor verdadero o falso."
    outputs = (OutputSpec("value", T.BOOLEAN),)
    params = (ParamSpec("value", ParamKind.BOOL, True, label="Valor", connectable=False),)

    def process(self, ctx, inputs, params):
        return {"value": params["value"]}

    def generate_code(self, gen, inputs, params):
        v = gen.new_var("flag")
        return CodeFragment([f"{v} = {params['value']!r}"], {"value": v})


@register_node
class ColorValue(NodeDefinition):
    type_id = "input.color"
    label = "Color"
    category = INPUT
    description = "Color RGB."
    outputs = (OutputSpec("color", T.COLOR),)
    params = (
        ParamSpec("color", ParamKind.COLOR, (255, 255, 255), label="Color", connectable=False),
    )

    def process(self, ctx, inputs, params):
        return {"color": params["color"]}

    def generate_code(self, gen, inputs, params):
        v = gen.new_var("color_rgb")
        return CodeFragment([f"{v} = {tuple(params['color'])!r}"], {"color": v})


VIDEO_FILTER = "Video (*.mp4 *.avi *.mov *.mkv *.webm);;Todos (*)"


@register_node
class LoadVideo(NodeDefinition):
    type_id = "input.load_video"
    label = "Load Video"
    category = INPUT
    description = (
        "Fuente de fotogramas desde un archivo de video. En tiempo real entrega un "
        "fotograma por iteración; en modo estático muestra el primero."
    )
    is_source = True
    outputs = (OutputSpec("image", T.IMAGE, "Fotograma"),)
    params = (
        ParamSpec("path", ParamKind.FILE_PATH, "", label="Archivo", file_filter=VIDEO_FILTER),
        ParamSpec("loop", ParamKind.BOOL, False, label="Repetir", connectable=False),
    )

    @classmethod
    def cache_key_extra(cls, params):
        try:
            stat = os.stat(params["path"])
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    @classmethod
    def open_source(cls, params):
        return CaptureSource(open_video_capture(params["path"]), loop=params["loop"], paced=True)

    def process(self, ctx, inputs, params):
        frame = ctx.frames.get(ctx.node_id)
        if frame is None:  # modo estático: primer fotograma
            source = self.open_source({**params, "loop": False})
            try:
                frame = source.read()
            finally:
                source.release()
            if frame is None:
                raise ValueError("El video no tiene fotogramas")
        return {"image": frame}

    def generate_code(self, gen, inputs, params):
        gen.helper("open_video_capture")
        gen.helper("read_frame")
        cap, frame = gen.new_var("video"), gen.new_var("frame")
        return CodeFragment(
            [
                f"{frame} = read_frame({cap}, {params['loop']!r})",
                f"if {frame} is None:",
                "    break  # fin del video",
            ],
            {"image": frame},
            pre=[f"{cap} = None"],
            setup=[f"{cap} = open_video_capture({params['path']!r})"],
            cleanup=[f"if {cap} is not None:", f"    {cap}.release()"],
        )

    @classmethod
    def export_problems(cls, params):
        return [] if params["path"] else ["no se ha seleccionado ningún archivo de video"]


@register_node
class Webcam(NodeDefinition):
    type_id = "input.webcam"
    label = "Webcam"
    category = INPUT
    description = "Fotogramas de una cámara. Solo funciona en tiempo real (Ejecutar, F5)."
    is_source = True
    outputs = (OutputSpec("image", T.IMAGE, "Fotograma"),)
    params = (
        ParamSpec(
            "index", ParamKind.INT, 0, label="Cámara", minimum=0, maximum=9, connectable=False
        ),
    )

    @classmethod
    def open_source(cls, params):
        return CaptureSource(open_camera_capture(params["index"]))

    def process(self, ctx, inputs, params):
        frame = ctx.frames.get(ctx.node_id)
        if frame is None:
            raise ValueError("La cámara solo funciona en tiempo real: pulsa Ejecutar (F5)")
        return {"image": frame}

    def generate_code(self, gen, inputs, params):
        gen.helper("open_camera_capture")
        gen.helper("read_frame")
        cap, frame = gen.new_var("camera"), gen.new_var("frame")
        return CodeFragment(
            [
                f"{frame} = read_frame({cap})",
                f"if {frame} is None:",
                "    break  # la cámara dejó de entregar fotogramas",
            ],
            {"image": frame},
            pre=[f"{cap} = None"],
            setup=[f"{cap} = open_camera_capture({params['index']})"],
            cleanup=[f"if {cap} is not None:", f"    {cap}.release()"],
        )


@register_node
class Vector2Value(NodeDefinition):
    type_id = "input.vector2"
    label = "Vector2"
    category = INPUT
    description = "Vector de dos componentes."
    outputs = (OutputSpec("vector", T.VECTOR2, "Vector"),)
    params = (ParamSpec("value", ParamKind.VECTOR2, (0.0, 0.0), label="Valor", connectable=False),)

    def process(self, ctx, inputs, params):
        return {"vector": params["value"]}

    def generate_code(self, gen, inputs, params):
        v = gen.new_var("vector2")
        return CodeFragment([f"{v} = {tuple(params['value'])!r}"], {"vector": v})


@register_node
class Vector3Value(NodeDefinition):
    type_id = "input.vector3"
    label = "Vector3"
    category = INPUT
    description = "Vector de tres componentes."
    outputs = (OutputSpec("vector", T.VECTOR3, "Vector"),)
    params = (
        ParamSpec("value", ParamKind.VECTOR3, (0.0, 0.0, 0.0), label="Valor", connectable=False),
    )

    def process(self, ctx, inputs, params):
        return {"vector": params["value"]}

    def generate_code(self, gen, inputs, params):
        v = gen.new_var("vector3")
        return CodeFragment([f"{v} = {tuple(params['value'])!r}"], {"vector": v})
