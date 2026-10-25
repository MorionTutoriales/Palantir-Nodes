"""Construye un tipo de nodo (``NodeDefinition``) a partir de un nodo personalizado."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from palantir_nodes.customnodes.analysis import Analysis
from palantir_nodes.customnodes.runtime import (
    FACTORY_NAME,
    call_user_function,
    coerce_results,
    compile_node_function,
    factory_source,
)
from palantir_nodes.customnodes.spec import CustomNodeSpec, slugify
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec

# Líneas que el script exportado necesita para que el código del usuario encuentre los mismos
# nombres que en la aplicación (ver ``runtime.build_namespace``).
PRELUDE = (
    "from typing import Any, Literal",
    "Image = np.ndarray",
    "Color = tuple",
    "Vector2 = tuple",
    "Vector3 = tuple",
)


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _prelude_for_imports(gen, spec, analysis) -> None:
    """Rutas de importación y paquetes que necesita el código del nodo en el script exportado."""
    import ast
    import sys

    from palantir_nodes.customnodes.analysis import imported_modules
    from palantir_nodes.customnodes.paths import applied_paths

    try:
        modules = [m for m, _ in imported_modules(ast.parse(spec.code))]
    except SyntaxError:
        return
    extra = [m for m in modules if m not in sys.stdlib_module_names and m not in ("numpy", "cv2")]
    if extra:
        gen.add_prelude(
            f"# Paquetes que importan los nodos personalizados: {', '.join(sorted(set(extra)))}"
        )
    for folder in applied_paths():
        gen.add_prelude(f"sys.path.append({folder!r})  # ruta de importación de la aplicación")


def build_node_class(spec: CustomNodeSpec, analysis: Analysis) -> type[NodeDefinition]:
    """Crea la clase del nodo. ``analysis`` debe haberse hecho sobre ``spec.code`` y ser válido."""
    if not analysis.ok:
        raise ValueError("No se puede crear un nodo con código que tiene errores")

    inputs = tuple(
        InputSpec(
            p.name,
            p.socket_type,
            default=None if p.optional or p.default is None else p.default,
            optional=p.optional,
        )
        for p in analysis.params
        if p.kind == "input"
    )
    params = tuple(
        ParamSpec(
            p.name,
            ParamKind.ENUM,
            p.default,
            label=_humanize(p.name),
            options=tuple((option, option) for option in p.options),
        )
        for p in analysis.params
        if p.kind == "enum"
    )
    outputs = tuple(
        OutputSpec(o.name, o.socket_type, label="Resultado" if o.name == "result" else "")
        for o in analysis.outputs
    )
    types = tuple(o.socket_type.value for o in analysis.outputs)
    label = spec.label
    state: dict[str, Callable[..., Any] | None] = {"fn": None}
    lock = threading.Lock()

    def user_function() -> Callable[..., Any]:
        with lock:  # el código del módulo se ejecuta una sola vez, en la primera ejecución
            if state["fn"] is None:
                state["fn"] = compile_node_function(spec.code, analysis.function_name, label)
            return state["fn"]

    def process(self, ctx, inputs_, params_):
        if not outputs and not ctx.side_effects:
            return {}  # sin salidas: solo actúa al ejecutar de forma explícita (como Save Image)
        kwargs = {
            p.name: (params_[p.name] if p.kind == "enum" else inputs_[p.name])
            for p in analysis.params
        }
        result = call_user_function(user_function(), kwargs, label)
        values = coerce_results(result, types, label)
        return {o.name: value for o, value in zip(analysis.outputs, values, strict=True)}

    def generate_code(self, gen, inputs_, params_):
        slug = slugify(label)
        gen.helper("coerce_results")
        fn_name, is_new = gen.define_once(f"{spec.id}:{spec.code_hash}", f"{slug}_fn")
        if is_new:
            make = gen.new_var(f"make_{slug}")
            for line in PRELUDE:
                gen.add_prelude(line)
            _prelude_for_imports(gen, spec, analysis)
            source = factory_source(spec.code, analysis.function_name)
            source = source.replace(f"def {FACTORY_NAME}():", f"def {make}():", 1)
            gen.add_module_code(
                [
                    f"# Nodo personalizado: {label}",
                    source.rstrip("\n"),
                    "",
                    "",
                    f"{fn_name} = {make}()",
                ]
            )
        arguments = []
        for p in analysis.params:
            value = inputs_[p.name] if p.kind == "input" else repr(params_[p.name])
            arguments.append(f"{p.name}={value}")
        args = ", ".join(arguments)
        call = f"{fn_name}({args})"
        if not outputs:
            return CodeFragment([call], {})
        names = [gen.new_var(o.name) for o in analysis.outputs]
        coerced = f"coerce_results({call}, {types!r}, {label!r})"
        if len(names) == 1:
            line = f"{names[0]} = {coerced}[0]"
        else:
            line = f"{', '.join(names)} = {coerced}"
        mapping = {o.name: n for o, n in zip(analysis.outputs, names, strict=True)}
        return CodeFragment([line], mapping)

    attributes = {
        "type_id": spec.id,
        "label": spec.label,
        "category": spec.category,
        "description": spec.description or analysis.description or spec.label,
        "inputs": inputs,
        "outputs": outputs,
        "params": params,
        "cacheable": bool(outputs) and not spec.always_run,
        "custom_spec": spec,
        "custom_analysis": analysis,
        "process": process,
        "generate_code": generate_code,
        "cache_key_extra": classmethod(lambda cls, params_: (spec.code_hash,)),
    }
    return type(f"CustomNode_{slugify(spec.id)}", (NodeDefinition,), attributes)
