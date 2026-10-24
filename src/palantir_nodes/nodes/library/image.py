"""Nodos de procesamiento de imágenes."""

import cv2
import numpy as np

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import IMAGE
from palantir_nodes.nodes.library._cv import (
    INTERPOLATION,
    KERNEL_SHAPES,
    as_bgr,
    as_gray,
    image_in,
    odd,
    rgb_to_bgr,
)
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec

INTERPOLATION_OPTIONS = (
    ("linear", "Lineal"),
    ("nearest", "Vecino más cercano"),
    ("cubic", "Cúbica"),
    ("area", "Área"),
    ("lanczos", "Lanczos"),
)
SHAPE_OPTIONS = (("rect", "Rectángulo"), ("ellipse", "Elipse"), ("cross", "Cruz"))


def _kernel(params) -> np.ndarray:
    size = max(1, int(params["ksize"]))
    return cv2.getStructuringElement(KERNEL_SHAPES[params["shape"]], (size, size))


def _morph_params(default_op: str | None = None) -> tuple[ParamSpec, ...]:
    specs = [
        ParamSpec("ksize", ParamKind.INT, 3, label="Kernel", minimum=1, maximum=99),
        ParamSpec("shape", ParamKind.ENUM, "rect", label="Forma", options=SHAPE_OPTIONS),
        ParamSpec("iterations", ParamKind.INT, 1, label="Iteraciones", minimum=1, maximum=50),
    ]
    if default_op:
        specs.insert(
            0,
            ParamSpec(
                "op",
                ParamKind.ENUM,
                default_op,
                label="Operación",
                options=(
                    ("open", "Apertura"),
                    ("close", "Cierre"),
                    ("gradient", "Gradiente"),
                    ("tophat", "Top Hat"),
                    ("blackhat", "Black Hat"),
                ),
            ),
        )
    return tuple(specs)


@register_node
class Grayscale(NodeDefinition):
    type_id = "image.grayscale"
    label = "Grayscale"
    category = IMAGE
    description = "Convierte la imagen a escala de grises."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)

    def process(self, ctx, inputs, params):
        return {"image": as_gray(image_in(inputs["image"]))}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_gray")
        o = gen.new_var("gray")
        return CodeFragment([f"{o} = as_gray({inputs['image']})"], {"image": o})


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

    def process(self, ctx, inputs, params):
        k = odd(params["ksize"])
        return {"image": cv2.GaussianBlur(image_in(inputs["image"]), (k, k), params["sigma"])}

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("blurred")
        k = odd(params["ksize"])
        line = f"{o} = cv2.GaussianBlur({inputs['image']}, ({k}, {k}), {params['sigma']!r})"
        return CodeFragment([line], {"image": o})


@register_node
class MedianBlur(NodeDefinition):
    type_id = "image.median_blur"
    label = "Median Blur"
    category = IMAGE
    description = "Filtro de mediana (elimina ruido sal y pimienta)."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "ksize", ParamKind.INT, 5, label="Kernel", minimum=3, maximum=99, step=2, slider=True
        ),
    )

    def process(self, ctx, inputs, params):
        return {"image": cv2.medianBlur(image_in(inputs["image"]), odd(params["ksize"], 3))}

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("median")
        line = f"{o} = cv2.medianBlur({inputs['image']}, {odd(params['ksize'], 3)})"
        return CodeFragment([line], {"image": o})


_THRESH_TYPES = {
    "binary": cv2.THRESH_BINARY,
    "binary_inv": cv2.THRESH_BINARY_INV,
    "trunc": cv2.THRESH_TRUNC,
    "tozero": cv2.THRESH_TOZERO,
    "tozero_inv": cv2.THRESH_TOZERO_INV,
}


@register_node
class Threshold(NodeDefinition):
    type_id = "image.threshold"
    label = "Threshold"
    category = IMAGE
    description = "Umbral global (convierte a gris si hace falta)."
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

    def process(self, ctx, inputs, params):
        gray = as_gray(image_in(inputs["image"]))
        flags = _THRESH_TYPES[params["method"]]
        if params["otsu"]:
            flags |= cv2.THRESH_OTSU
        used, out = cv2.threshold(gray, params["thresh"], params["maxval"], flags)
        return {"image": out, "threshold": float(used)}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_gray")
        o = gen.new_var("thresholded")
        used = gen.new_var("used_threshold") if gen.wanted("threshold") else "_"
        flags = "cv2.THRESH_" + params["method"].upper()
        if params["otsu"]:
            flags += " | cv2.THRESH_OTSU"
        line = (
            f"{used}, {o} = cv2.threshold(as_gray({inputs['image']}), "
            f"{params['thresh']!r}, {params['maxval']!r}, {flags})"
        )
        return CodeFragment([line], {"image": o, "threshold": f"float({used})"})


@register_node
class AdaptiveThreshold(NodeDefinition):
    type_id = "image.adaptive_threshold"
    label = "Adaptive Threshold"
    category = IMAGE
    description = "Umbral adaptativo por vecindad."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec("maxval", ParamKind.FLOAT, 255.0, label="Valor máx.", minimum=0, maximum=255),
        ParamSpec(
            "method",
            ParamKind.ENUM,
            "gaussian",
            label="Método",
            options=(("mean", "Media"), ("gaussian", "Gaussiano")),
        ),
        ParamSpec(
            "type",
            ParamKind.ENUM,
            "binary",
            label="Tipo",
            options=(("binary", "Binary"), ("binary_inv", "Binary Inv")),
        ),
        ParamSpec("block_size", ParamKind.INT, 11, label="Bloque", minimum=3, maximum=201, step=2),
        ParamSpec("c", ParamKind.FLOAT, 2.0, label="C", minimum=-100, maximum=100),
    )

    def process(self, ctx, inputs, params):
        gray = as_gray(image_in(inputs["image"]))
        method = (
            cv2.ADAPTIVE_THRESH_MEAN_C
            if params["method"] == "mean"
            else cv2.ADAPTIVE_THRESH_GAUSSIAN_C
        )
        kind = cv2.THRESH_BINARY if params["type"] == "binary" else cv2.THRESH_BINARY_INV
        out = cv2.adaptiveThreshold(
            gray, params["maxval"], method, kind, odd(params["block_size"], 3), params["c"]
        )
        return {"image": out}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_gray")
        o = gen.new_var("adaptive")
        method = (
            "cv2.ADAPTIVE_THRESH_MEAN_C"
            if params["method"] == "mean"
            else ("cv2.ADAPTIVE_THRESH_GAUSSIAN_C")
        )
        kind = "cv2.THRESH_BINARY" if params["type"] == "binary" else "cv2.THRESH_BINARY_INV"
        line = (
            f"{o} = cv2.adaptiveThreshold(as_gray({inputs['image']}), {params['maxval']!r}, "
            f"{method}, {kind}, {odd(params['block_size'], 3)}, {params['c']!r})"
        )
        return CodeFragment([line], {"image": o})


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

    def process(self, ctx, inputs, params):
        gray = as_gray(image_in(inputs["image"]))
        edges = cv2.Canny(
            gray,
            params["threshold1"],
            params["threshold2"],
            apertureSize=int(params["aperture"]),
            L2gradient=params["l2_gradient"],
        )
        return {"edges": edges}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_gray")
        o = gen.new_var("edges")
        line = (
            f"{o} = cv2.Canny(as_gray({inputs['image']}), {params['threshold1']!r}, "
            f"{params['threshold2']!r}, apertureSize={int(params['aperture'])}, "
            f"L2gradient={params['l2_gradient']!r})"
        )
        return CodeFragment([line], {"edges": o})


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
            "interpolation",
            ParamKind.ENUM,
            "linear",
            label="Interpolación",
            options=INTERPOLATION_OPTIONS,
        ),
    )

    def process(self, ctx, inputs, params):
        img = image_in(inputs["image"])
        if params["mode"] == "scale":
            w = max(1, round(img.shape[1] * params["scale"]))
            h = max(1, round(img.shape[0] * params["scale"]))
        else:
            w, h = params["width"], params["height"]
        return {
            "image": cv2.resize(img, (w, h), interpolation=INTERPOLATION[params["interpolation"]])
        }

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("resized")
        img = inputs["image"]
        interp = (
            "cv2.INTER_"
            + {
                "linear": "LINEAR",
                "nearest": "NEAREST",
                "cubic": "CUBIC",
                "area": "AREA",
                "lanczos": "LANCZOS4",
            }[params["interpolation"]]
        )
        if params["mode"] == "scale":
            s = params["scale"]
            size = f"(max(1, round({img}.shape[1] * {s!r})), max(1, round({img}.shape[0] * {s!r})))"
        else:
            size = f"({params['width']}, {params['height']})"
        line = f"{o} = cv2.resize({img}, {size}, interpolation={interp})"
        return CodeFragment([line], {"image": o})


@register_node
class Crop(NodeDefinition):
    type_id = "image.crop"
    label = "Crop"
    category = IMAGE
    description = "Recorta una región rectangular."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec("x", ParamKind.INT, 0, label="X", minimum=0, maximum=65535),
        ParamSpec("y", ParamKind.INT, 0, label="Y", minimum=0, maximum=65535),
        ParamSpec("width", ParamKind.INT, 100, label="Ancho", minimum=1, maximum=65535),
        ParamSpec("height", ParamKind.INT, 100, label="Alto", minimum=1, maximum=65535),
    )

    def process(self, ctx, inputs, params):
        img = image_in(inputs["image"])
        h, w = img.shape[:2]
        x, y = params["x"], params["y"]
        if x >= w or y >= h:
            raise ValueError(f"El recorte queda fuera de la imagen ({w}×{h})")
        return {"image": img[y : y + params["height"], x : x + params["width"]].copy()}

    def generate_code(self, gen, inputs, params):
        img = inputs["image"]
        h, w, o = gen.new_var("height"), gen.new_var("width"), gen.new_var("cropped")
        x, y = params["x"], params["y"]
        lines = [
            f"{h}, {w} = {img}.shape[:2]",
            f"if {x} >= {w} or {y} >= {h}:",
            f'    raise ValueError(f"El recorte queda fuera de la imagen ({{{w}}}×{{{h}}})")',
            f"{o} = {img}[{y}:{y} + {params['height']}, {x}:{x} + {params['width']}].copy()",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class Rotate(NodeDefinition):
    type_id = "image.rotate"
    label = "Rotate"
    category = IMAGE
    description = "Rota la imagen alrededor de su centro (positivo = antihorario)."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "angle", ParamKind.FLOAT, 0.0, label="Ángulo", minimum=-360, maximum=360, slider=True
        ),
        ParamSpec("expand", ParamKind.BOOL, False, label="Ampliar lienzo"),
        ParamSpec(
            "interpolation",
            ParamKind.ENUM,
            "linear",
            label="Interpolación",
            options=INTERPOLATION_OPTIONS,
        ),
    )

    def process(self, ctx, inputs, params):
        img = image_in(inputs["image"])
        h, w = img.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), params["angle"], 1.0)
        new_w, new_h = w, h
        if params["expand"]:
            cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
            new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
            matrix[0, 2] += new_w / 2 - w / 2
            matrix[1, 2] += new_h / 2 - h / 2
        out = cv2.warpAffine(
            img,
            matrix,
            (max(1, new_w), max(1, new_h)),
            flags=INTERPOLATION[params["interpolation"]],
        )
        return {"image": out}

    def generate_code(self, gen, inputs, params):
        img = inputs["image"]
        h, w, m, o = (gen.new_var(n) for n in ("height", "width", "rotation", "rotated"))
        interp = (
            "cv2.INTER_"
            + {
                "linear": "LINEAR",
                "nearest": "NEAREST",
                "cubic": "CUBIC",
                "area": "AREA",
                "lanczos": "LANCZOS4",
            }[params["interpolation"]]
        )
        lines = [
            f"{h}, {w} = {img}.shape[:2]",
            f"{m} = cv2.getRotationMatrix2D(({w} / 2, {h} / 2), {params['angle']!r}, 1.0)",
        ]
        new_w, new_h = w, h
        if params["expand"]:
            new_w, new_h = gen.new_var("new_width"), gen.new_var("new_height")
            lines += [
                f"{new_w} = int({h} * abs({m}[0, 1]) + {w} * abs({m}[0, 0]))",
                f"{new_h} = int({h} * abs({m}[0, 0]) + {w} * abs({m}[0, 1]))",
                f"{m}[0, 2] += {new_w} / 2 - {w} / 2",
                f"{m}[1, 2] += {new_h} / 2 - {h} / 2",
            ]
        lines.append(
            f"{o} = cv2.warpAffine({img}, {m}, (max(1, {new_w}), max(1, {new_h})), flags={interp})"
        )
        return CodeFragment(lines, {"image": o})


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

    def process(self, ctx, inputs, params):
        code = {"horizontal": 1, "vertical": 0, "both": -1}[params["axis"]]
        return {"image": cv2.flip(image_in(inputs["image"]), code)}

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("flipped")
        code = {"horizontal": 1, "vertical": 0, "both": -1}[params["axis"]]
        return CodeFragment([f"{o} = cv2.flip({inputs['image']}, {code})"], {"image": o})


@register_node
class HsvConversion(NodeDefinition):
    type_id = "image.hsv"
    label = "HSV Conversion"
    category = IMAGE
    description = "Convierte entre BGR y HSV (H: 0-179, S y V: 0-255)."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec(
            "direction",
            ParamKind.ENUM,
            "bgr2hsv",
            label="Dirección",
            options=(("bgr2hsv", "BGR → HSV"), ("hsv2bgr", "HSV → BGR")),
        ),
    )

    def process(self, ctx, inputs, params):
        img = image_in(inputs["image"])
        if params["direction"] == "bgr2hsv":
            return {"image": cv2.cvtColor(as_bgr(img), cv2.COLOR_BGR2HSV)}
        if img.ndim != 3 or img.shape[2] != 3:
            raise ValueError("HSV → BGR necesita una imagen de 3 canales")
        return {"image": cv2.cvtColor(img, cv2.COLOR_HSV2BGR)}

    def generate_code(self, gen, inputs, params):
        img = inputs["image"]
        if params["direction"] == "bgr2hsv":
            gen.helper("as_bgr")
            o = gen.new_var("hsv")
            return CodeFragment(
                [f"{o} = cv2.cvtColor(as_bgr({img}), cv2.COLOR_BGR2HSV)"], {"image": o}
            )
        o = gen.new_var("bgr")
        lines = [
            f"if {img}.ndim != 3 or {img}.shape[2] != 3:",
            '    raise ValueError("HSV → BGR necesita una imagen de 3 canales")',
            f"{o} = cv2.cvtColor({img}, cv2.COLOR_HSV2BGR)",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class InRange(NodeDefinition):
    type_id = "image.in_range"
    label = "Color Range (InRange)"
    category = IMAGE
    description = "Máscara de los píxeles dentro de un rango de color."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("mask", T.IMAGE, "Máscara"),)
    params = (
        ParamSpec("use_hsv", ParamKind.BOOL, True, label="Convertir a HSV"),
        ParamSpec(
            "lower",
            ParamKind.VECTOR3,
            (0.0, 0.0, 0.0),
            label="Mínimo",
            minimum=0,
            maximum=255,
            tooltip="Con HSV: H 0-179, S 0-255, V 0-255. Sin HSV: B, G, R.",
        ),
        ParamSpec(
            "upper",
            ParamKind.VECTOR3,
            (179.0, 255.0, 255.0),
            label="Máximo",
            minimum=0,
            maximum=255,
        ),
    )

    def process(self, ctx, inputs, params):
        img = as_bgr(image_in(inputs["image"]))
        if params["use_hsv"]:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower = np.clip(np.rint(params["lower"]), 0, 255).astype(np.uint8)
        upper = np.clip(np.rint(params["upper"]), 0, 255).astype(np.uint8)
        return {"mask": cv2.inRange(img, lower, upper)}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_bgr")
        src, o = gen.new_var("source"), gen.new_var("mask")
        lines = [f"{src} = as_bgr({inputs['image']})"]
        if params["use_hsv"]:
            lines.append(f"{src} = cv2.cvtColor({src}, cv2.COLOR_BGR2HSV)")

        def bounds(vec):
            return [int(max(0, min(255, round(v)))) for v in vec]

        lines.append(
            f"{o} = cv2.inRange({src}, np.array({bounds(params['lower'])!r}, dtype=np.uint8), "
            f"np.array({bounds(params['upper'])!r}, dtype=np.uint8))"
        )
        return CodeFragment(lines, {"mask": o})


@register_node
class Erode(NodeDefinition):
    type_id = "image.erode"
    label = "Erode"
    category = IMAGE
    description = "Erosión morfológica."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = _morph_params()

    def process(self, ctx, inputs, params):
        out = cv2.erode(image_in(inputs["image"]), _kernel(params), iterations=params["iterations"])
        return {"image": out}

    def generate_code(self, gen, inputs, params):
        k, o = gen.new_var("kernel"), gen.new_var("eroded")
        size = max(1, int(params["ksize"]))
        lines = [
            f"{k} = cv2.getStructuringElement("
            f"cv2.MORPH_{params['shape'].upper()}, ({size}, {size}))",
            f"{o} = cv2.erode({inputs['image']}, {k}, iterations={params['iterations']})",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class Dilate(NodeDefinition):
    type_id = "image.dilate"
    label = "Dilate"
    category = IMAGE
    description = "Dilatación morfológica."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = _morph_params()

    def process(self, ctx, inputs, params):
        out = cv2.dilate(
            image_in(inputs["image"]), _kernel(params), iterations=params["iterations"]
        )
        return {"image": out}

    def generate_code(self, gen, inputs, params):
        k, o = gen.new_var("kernel"), gen.new_var("dilated")
        size = max(1, int(params["ksize"]))
        lines = [
            f"{k} = cv2.getStructuringElement("
            f"cv2.MORPH_{params['shape'].upper()}, ({size}, {size}))",
            f"{o} = cv2.dilate({inputs['image']}, {k}, iterations={params['iterations']})",
        ]
        return CodeFragment(lines, {"image": o})


_MORPH_OPS = {
    "open": cv2.MORPH_OPEN,
    "close": cv2.MORPH_CLOSE,
    "gradient": cv2.MORPH_GRADIENT,
    "tophat": cv2.MORPH_TOPHAT,
    "blackhat": cv2.MORPH_BLACKHAT,
}


@register_node
class MorphologyEx(NodeDefinition):
    type_id = "image.morphology"
    label = "Morphological Operations"
    category = IMAGE
    description = "Apertura, cierre, gradiente, top hat y black hat."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (OutputSpec("image", T.IMAGE),)
    params = _morph_params("open")

    def process(self, ctx, inputs, params):
        out = cv2.morphologyEx(
            image_in(inputs["image"]),
            _MORPH_OPS[params["op"]],
            _kernel(params),
            iterations=params["iterations"],
        )
        return {"image": out}

    def generate_code(self, gen, inputs, params):
        k, o = gen.new_var("kernel"), gen.new_var("morphed")
        size = max(1, int(params["ksize"]))
        op = {
            "open": "OPEN",
            "close": "CLOSE",
            "gradient": "GRADIENT",
            "tophat": "TOPHAT",
            "blackhat": "BLACKHAT",
        }[params["op"]]
        lines = [
            f"{k} = cv2.getStructuringElement("
            f"cv2.MORPH_{params['shape'].upper()}, ({size}, {size}))",
            f"{o} = cv2.morphologyEx({inputs['image']}, cv2.MORPH_{op}, {k}, "
            f"iterations={params['iterations']})",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class FindContours(NodeDefinition):
    type_id = "image.find_contours"
    label = "Find Contours"
    category = IMAGE
    description = "Encuentra contornos en una imagen binaria (todo lo distinto de 0 cuenta)."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (
        OutputSpec("contours", T.ANY, "Contornos"),
        OutputSpec("count", T.INTEGER, "Cantidad"),
    )
    params = (
        ParamSpec(
            "mode",
            ParamKind.ENUM,
            "external",
            label="Modo",
            options=(
                ("external", "Externos"),
                ("list", "Todos (lista)"),
                ("ccomp", "Dos niveles"),
                ("tree", "Árbol"),
            ),
        ),
        ParamSpec(
            "method",
            ParamKind.ENUM,
            "simple",
            label="Aproximación",
            options=(("simple", "Simple"), ("none", "Todos los puntos")),
        ),
    )

    def process(self, ctx, inputs, params):
        gray = as_gray(image_in(inputs["image"]))
        mode = {
            "external": cv2.RETR_EXTERNAL,
            "list": cv2.RETR_LIST,
            "ccomp": cv2.RETR_CCOMP,
            "tree": cv2.RETR_TREE,
        }[params["mode"]]
        method = cv2.CHAIN_APPROX_SIMPLE if params["method"] == "simple" else cv2.CHAIN_APPROX_NONE
        found = cv2.findContours(gray.copy(), mode, method)
        contours = tuple(found[-2])  # (contours, hierarchy) o (image, contours, hierarchy)
        return {"contours": contours, "count": len(contours)}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_gray")
        found, c = gen.new_var("found"), gen.new_var("contours")
        mode = "cv2.RETR_" + params["mode"].upper()
        method = (
            "cv2.CHAIN_APPROX_SIMPLE" if params["method"] == "simple" else ("cv2.CHAIN_APPROX_NONE")
        )
        lines = [
            f"{found} = cv2.findContours(as_gray({inputs['image']}).copy(), {mode}, {method})",
            f"{c} = tuple({found}[-2])",
        ]
        return CodeFragment(lines, {"contours": c, "count": f"len({c})"})


@register_node
class DrawContours(NodeDefinition):
    type_id = "image.draw_contours"
    label = "Draw Contours"
    category = IMAGE
    description = "Dibuja contornos sobre una imagen."
    inputs = (
        InputSpec("image", T.IMAGE),
        InputSpec("contours", T.ANY, "Contornos"),
    )
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec("color", ParamKind.COLOR, (0, 255, 0), label="Color"),
        ParamSpec(
            "thickness",
            ParamKind.INT,
            2,
            label="Grosor",
            minimum=-1,
            maximum=50,
            tooltip="-1 rellena el contorno.",
        ),
        ParamSpec(
            "index",
            ParamKind.INT,
            -1,
            label="Índice",
            minimum=-1,
            maximum=100000,
            tooltip="-1 dibuja todos.",
        ),
    )

    def process(self, ctx, inputs, params):
        contours = inputs["contours"]
        if not isinstance(contours, (list, tuple)):
            raise ValueError("La entrada 'Contornos' no proviene de Find Contours")
        canvas = np.array(as_bgr(image_in(inputs["image"])))  # copia: la entrada es de solo lectura
        cv2.drawContours(
            canvas,
            list(contours),
            params["index"],
            rgb_to_bgr(params["color"]),
            params["thickness"],
        )
        return {"image": canvas}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_bgr")
        o = gen.new_var("drawn")
        bgr = rgb_to_bgr(params["color"])
        lines = [
            f"{o} = np.array(as_bgr({inputs['image']}))",
            f"cv2.drawContours({o}, list({inputs['contours']}), {params['index']}, {bgr!r}, "
            f"{params['thickness']})",
        ]
        return CodeFragment(lines, {"image": o})
