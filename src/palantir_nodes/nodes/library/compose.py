"""Nodos de composición."""

import cv2
import numpy as np

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import CodeFragment, Expr, NodeDefinition
from palantir_nodes.nodes.categories import COMPOSITE
from palantir_nodes.nodes.library._cv import as_bgr, as_gray, image_in, match
from palantir_nodes.nodes.registry import register_node
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec

_AB = (InputSpec("image_a", T.IMAGE, "Imagen A"), InputSpec("image_b", T.IMAGE, "Imagen B"))
_IMAGE_OUT = (OutputSpec("image", T.IMAGE),)


def _pair(inputs) -> tuple[np.ndarray, np.ndarray]:
    return match(image_in(inputs["image_a"], "Imagen A"), image_in(inputs["image_b"], "Imagen B"))


@register_node
class BlendImages(NodeDefinition):
    type_id = "compose.blend"
    label = "Blend Images"
    category = COMPOSITE
    description = "Mezcla dos imágenes (B se ajusta al tamaño de A)."
    inputs = (InputSpec("factor", T.FLOAT, "Factor", default=0.5, minimum=0.0, maximum=1.0), *_AB)
    outputs = _IMAGE_OUT
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

    def process(self, ctx, inputs, params):
        a, b = _pair(inputs)
        f = float(np.clip(inputs["factor"], 0.0, 1.0))
        af, bf = a.astype(np.float32), b.astype(np.float32)
        match params["mode"]:
            case "mix":
                out = af * (1 - f) + bf * f
            case "add":
                out = af + bf * f
            case "multiply":
                out = af * (1 - f) + (af * bf / 255.0) * f
            case _:  # screen
                out = af * (1 - f) + (255.0 - (255.0 - af) * (255.0 - bf) / 255.0) * f
        return {"image": np.clip(np.rint(out), 0, 255).astype(np.uint8)}

    def generate_code(self, gen, inputs, params):
        gen.helper("match")
        a, b, f, af, bf, o = (
            gen.new_var(n) for n in ("a", "b", "factor", "a_float", "b_float", "blended")
        )
        expr = {
            "mix": f"{af} * (1 - {f}) + {bf} * {f}",
            "add": f"{af} + {bf} * {f}",
            "multiply": f"{af} * (1 - {f}) + ({af} * {bf} / 255.0) * {f}",
            "screen": f"{af} * (1 - {f}) + (255.0 - (255.0 - {af}) * (255.0 - {bf}) / 255.0) * {f}",
        }[params["mode"]]
        lines = [
            f"{a}, {b} = match({inputs['image_a']}, {inputs['image_b']})",
            f"{f} = float(np.clip({inputs['factor']}, 0.0, 1.0))",
            f"{af} = {a}.astype(np.float32)",
            f"{bf} = {b}.astype(np.float32)",
            f"{o} = np.clip(np.rint({expr}), 0, 255).astype(np.uint8)",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class AddWeighted(NodeDefinition):
    type_id = "compose.add_weighted"
    label = "Add Weighted"
    category = COMPOSITE
    description = "A·alfa + B·beta + gamma."
    inputs = (
        *_AB,
        InputSpec("alpha", T.FLOAT, "Alfa", default=0.5),
        InputSpec("beta", T.FLOAT, "Beta", default=0.5),
        InputSpec("gamma", T.FLOAT, "Gamma", default=0.0),
    )
    outputs = _IMAGE_OUT

    def process(self, ctx, inputs, params):
        a, b = _pair(inputs)
        out = cv2.addWeighted(a, inputs["alpha"], b, inputs["beta"], inputs["gamma"])
        return {"image": out}

    def generate_code(self, gen, inputs, params):
        gen.helper("match")
        a, b, o = gen.new_var("a"), gen.new_var("b"), gen.new_var("weighted")
        lines = [
            f"{a}, {b} = match({inputs['image_a']}, {inputs['image_b']})",
            f"{o} = cv2.addWeighted({a}, {inputs['alpha']}, {b}, {inputs['beta']}, "
            f"{inputs['gamma']})",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class BitwiseAnd(NodeDefinition):
    type_id = "compose.bitwise_and"
    label = "Bitwise AND"
    category = COMPOSITE
    description = "AND bit a bit entre dos imágenes."
    inputs = _AB
    outputs = _IMAGE_OUT

    def process(self, ctx, inputs, params):
        a, b = _pair(inputs)
        return {"image": cv2.bitwise_and(a, b)}

    def generate_code(self, gen, inputs, params):
        gen.helper("match")
        a, b, o = gen.new_var("a"), gen.new_var("b"), gen.new_var("anded")
        lines = [
            f"{a}, {b} = match({inputs['image_a']}, {inputs['image_b']})",
            f"{o} = cv2.bitwise_and({a}, {b})",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class BitwiseOr(NodeDefinition):
    type_id = "compose.bitwise_or"
    label = "Bitwise OR"
    category = COMPOSITE
    description = "OR bit a bit entre dos imágenes."
    inputs = _AB
    outputs = _IMAGE_OUT

    def process(self, ctx, inputs, params):
        a, b = _pair(inputs)
        return {"image": cv2.bitwise_or(a, b)}

    def generate_code(self, gen, inputs, params):
        gen.helper("match")
        a, b, o = gen.new_var("a"), gen.new_var("b"), gen.new_var("ored")
        lines = [
            f"{a}, {b} = match({inputs['image_a']}, {inputs['image_b']})",
            f"{o} = cv2.bitwise_or({a}, {b})",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class BitwiseNot(NodeDefinition):
    type_id = "compose.bitwise_not"
    label = "Bitwise NOT"
    category = COMPOSITE
    description = "Invierte los bits de la imagen."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = _IMAGE_OUT

    def process(self, ctx, inputs, params):
        return {"image": cv2.bitwise_not(image_in(inputs["image"]))}

    def generate_code(self, gen, inputs, params):
        o = gen.new_var("inverted")
        return CodeFragment([f"{o} = cv2.bitwise_not({inputs['image']})"], {"image": o})


@register_node
class MaskImage(NodeDefinition):
    type_id = "compose.mask"
    label = "Mask"
    category = COMPOSITE
    description = "Conserva los píxeles donde la máscara es distinta de 0."
    inputs = (InputSpec("image", T.IMAGE), InputSpec("mask", T.IMAGE, "Máscara"))
    outputs = _IMAGE_OUT
    params = (ParamSpec("invert", ParamKind.BOOL, False, label="Invertir máscara"),)

    def process(self, ctx, inputs, params):
        img = image_in(inputs["image"])
        mask = as_gray(image_in(inputs["mask"], "Máscara"))
        if mask.shape[:2] != img.shape[:2]:
            mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        keep = (mask == 0) if params["invert"] else (mask > 0)
        return {"image": cv2.bitwise_and(img, img, mask=keep.astype(np.uint8) * 255)}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_gray")
        img = inputs["image"]
        m, keep, o = gen.new_var("mask"), gen.new_var("keep"), gen.new_var("masked")
        invert = params["invert"]
        if isinstance(invert, Expr):  # se decide al ejecutar el script
            cond = f"(({m} == 0) if {invert} else ({m} > 0))"
        else:
            cond = f"({m} == 0)" if invert else f"({m} > 0)"
        lines = [
            f"{m} = as_gray({inputs['mask']})",
            f"if {m}.shape[:2] != {img}.shape[:2]:",
            f"    {m} = cv2.resize({m}, ({img}.shape[1], {img}.shape[0]), "
            "interpolation=cv2.INTER_NEAREST)",
            f"{keep} = {cond}",
            f"{o} = cv2.bitwise_and({img}, {img}, mask={keep}.astype(np.uint8) * 255)",
        ]
        return CodeFragment(lines, {"image": o})


@register_node
class MergeChannels(NodeDefinition):
    type_id = "compose.merge_channels"
    label = "Merge Channels"
    category = COMPOSITE
    description = "Combina tres canales en una imagen BGR."
    inputs = (
        InputSpec("blue", T.IMAGE, "Azul"),
        InputSpec("green", T.IMAGE, "Verde"),
        InputSpec("red", T.IMAGE, "Rojo"),
    )
    outputs = _IMAGE_OUT

    def process(self, ctx, inputs, params):
        blue = as_gray(image_in(inputs["blue"], "Azul"))
        channels = [blue]
        for name, label in (("green", "Verde"), ("red", "Rojo")):
            channel = as_gray(image_in(inputs[name], label))
            if channel.shape != blue.shape:
                channel = cv2.resize(channel, (blue.shape[1], blue.shape[0]))
            channels.append(channel)
        return {"image": cv2.merge(channels)}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_gray")
        b, g, r, o = (gen.new_var(n) for n in ("blue", "green", "red", "merged"))
        lines = [f"{b} = as_gray({inputs['blue']})"]
        for var, name in ((g, "green"), (r, "red")):
            lines += [
                f"{var} = as_gray({inputs[name]})",
                f"if {var}.shape != {b}.shape:",
                f"    {var} = cv2.resize({var}, ({b}.shape[1], {b}.shape[0]))",
            ]
        lines.append(f"{o} = cv2.merge([{b}, {g}, {r}])")
        return CodeFragment(lines, {"image": o})


@register_node
class SplitChannels(NodeDefinition):
    type_id = "compose.split_channels"
    label = "Split Channels"
    category = COMPOSITE
    description = "Separa una imagen en sus canales B, G y R."
    inputs = (InputSpec("image", T.IMAGE),)
    outputs = (
        OutputSpec("blue", T.IMAGE, "Azul"),
        OutputSpec("green", T.IMAGE, "Verde"),
        OutputSpec("red", T.IMAGE, "Rojo"),
    )

    def process(self, ctx, inputs, params):
        blue, green, red = cv2.split(as_bgr(image_in(inputs["image"])))
        return {"blue": blue, "green": green, "red": red}

    def generate_code(self, gen, inputs, params):
        gen.helper("as_bgr")
        b, g, r = gen.new_var("blue"), gen.new_var("green"), gen.new_var("red")
        line = f"{b}, {g}, {r} = cv2.split(as_bgr({inputs['image']}))"
        return CodeFragment([line], {"blue": b, "green": g, "red": r})
