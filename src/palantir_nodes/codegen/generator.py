"""Genera un script Python independiente a partir del plan de ejecución.

Usa el mismo ``ExecutionPlan`` y las mismas definiciones de nodo que el motor; cada
nodo aporta su fragmento con ``generate_code``. Si el grafo tiene fuentes de video o
cámara, el script procesa los fotogramas en un bucle y libera los recursos al terminar.
"""

from __future__ import annotations

import builtins
import keyword
import re
from typing import Any, NamedTuple

from palantir_nodes.codegen import helpers
from palantir_nodes.core.errors import PalantirError
from palantir_nodes.core.types import conversion_between
from palantir_nodes.engine.plan import ExecutionPlan, PlanNode
from palantir_nodes.nodes.base import Expr, NodeDefinition

_RESERVED = (
    set(keyword.kwlist)
    | set(dir(builtins))
    | set(helpers.HELPERS)
    | {"cv2", "np", "os", "sys", "main", "show", "node", "exc", "max_frames", "frame_count"}
    | {"args", "limit"}
)

_MAIN_STATIC = 'if __name__ == "__main__":\n    main(show="--no-show" not in sys.argv[1:])\n'
_MAIN_REALTIME = (
    'if __name__ == "__main__":\n'
    "    args = sys.argv[1:]\n"
    '    limit = int(args[args.index("--max-frames") + 1]) if "--max-frames" in args else 0\n'
    '    main(show="--no-show" not in args, max_frames=limit)\n'
)


class ExportProblem(NamedTuple):
    node_id: str | None
    message: str


class ExportError(PalantirError):
    def __init__(self, problems: list[ExportProblem]) -> None:
        self.problems = problems
        super().__init__("\n".join(p.message for p in problems))


def _indent(lines: list[str], level: int) -> list[str]:
    pad = " " * 4 * level
    return [(pad + line) if line else "" for line in lines]


class CodeGenerator:
    def __init__(self, plan: ExecutionPlan, version: str = "") -> None:
        self.plan = plan
        self.version = version
        self.uses_display = False
        self._used_names: set[str] = set()
        self._helpers: set[str] = set()
        self._wanted: set[str] = set()
        self._windows: dict[str, int] = {}

    # -- API para los nodos ------------------------------------------------------------

    def new_var(self, hint: str) -> str:
        """Nombre de variable válido y único dentro del script."""
        base = re.sub(r"[^0-9a-zA-Z_]+", "_", hint).strip("_").lower() or "value"
        if base[0].isdigit():
            base = f"v_{base}"
        name, n = base, 2
        while name in self._used_names or name in _RESERVED:
            name, n = f"{base}_{n}", n + 1
        self._used_names.add(name)
        return name

    def helper(self, name: str) -> None:
        self._helpers.add(name)

    def wanted(self, output: str) -> bool:
        """``True`` si alguna conexión usa esa salida del nodo que se está generando."""
        return output in self._wanted

    def lit(self, value: Any) -> str:
        return repr(value)

    def window_name(self, label: str) -> str:
        count = self._windows.get(label, 0) + 1
        self._windows[label] = count
        return label if count == 1 else f"{label} {count}"

    # -- generación --------------------------------------------------------------------

    def generate(self) -> str:
        plan = self.plan
        sinks = [i for i in plan.order if not plan.nodes[i].definition.outputs]
        if not sinks:
            raise ExportError(
                [
                    ExportProblem(
                        None, "El grafo no tiene nodos de salida (Image/Video Viewer o Save)."
                    )
                ]
            )
        needed = self._ancestors(sinks)
        problems = self._problems(needed)
        if problems:
            raise ExportError(problems)

        order = [i for i in plan.order if i in needed]
        consumed: dict[str, set[str]] = {i: set() for i in order}
        for dst in order:
            for src, sock in plan.incoming.get(dst, {}).values():
                consumed[src].add(sock)

        exprs: dict[tuple[str, str], str] = {}
        body: list[str] = []
        pre: list[str] = []
        setup: list[str] = []
        cleanup: list[str] = []
        realtime = any(plan.nodes[i].definition.is_source for i in order)
        for node_id in order:
            node = plan.nodes[node_id]
            definition = node.definition
            inputs = self._input_exprs(node, exprs)
            params, param_lines = self._param_exprs(node, exprs)
            self._wanted = consumed[node_id]
            fragment = definition().generate_code(self, inputs, params)
            fragment.lines = [*param_lines, *fragment.lines]
            for spec in definition.outputs:
                if spec.name in self._wanted:
                    exprs[(node_id, spec.name)] = fragment.outputs[spec.name]
            label = f"node = {definition.label!r}"
            body += [f"# --- {definition.label} ---", label]
            body += fragment.lines + [""]
            pre += fragment.pre
            cleanup += fragment.cleanup
            if fragment.setup:
                setup += [label, *fragment.setup]
        return self._assemble(body, pre, setup, cleanup, realtime)

    def _ancestors(self, sinks: list[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(sinks)
        while stack:
            node_id = stack.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            stack.extend(src for src, _ in self.plan.incoming.get(node_id, {}).values())
        return seen

    def _problems(self, needed: set[str]) -> list[ExportProblem]:
        problems: list[ExportProblem] = []
        for node_id in self.plan.order:
            if node_id not in needed:
                continue
            node = self.plan.nodes[node_id]
            d: type[NodeDefinition] = node.definition
            if d.generate_code is NodeDefinition.generate_code:
                problems.append(
                    ExportProblem(
                        node_id, f"'{d.label}' no tiene generación de código implementada"
                    )
                )
                continue
            connected = self.plan.incoming.get(node_id, {})
            for spec in d.inputs:
                if spec.name not in connected and not spec.has_default:
                    problems.append(
                        ExportProblem(
                            node_id, f"'{d.label}': falta conectar '{spec.display_label}'"
                        )
                    )
            problems += [
                ExportProblem(node_id, f"'{d.label}': {msg}")
                for msg in d.export_problems(node.params)
            ]
        return problems

    def _input_exprs(self, node: PlanNode, exprs: dict[tuple[str, str], str]) -> dict[str, str]:
        result: dict[str, str] = {}
        incoming = self.plan.incoming.get(node.id, {})
        for spec in node.definition.inputs:
            if spec.name in incoming:
                src_id, sock = incoming[spec.name]
                expr = exprs[(src_id, sock)]
                src_type = self.plan.nodes[src_id].definition.output(sock).type
                conv = conversion_between(src_type, spec.type)
                result[spec.name] = conv.template.format(expr) if conv else expr
            else:
                result[spec.name] = self.lit(node.input_values[spec.name])
        return result

    def _param_exprs(
        self, node: PlanNode, exprs: dict[tuple[str, str], str]
    ) -> tuple[dict[str, Any], list[str]]:
        """Parámetros del nodo para generar su código, y las líneas que calculan los conectados.

        Un parámetro cuyo socket está conectado se guarda en una variable (convertida y
        normalizada igual que lo hace el motor) y el nodo lo recibe como :class:`Expr`.
        """
        params: dict[str, Any] = dict(node.params)
        lines: list[str] = []
        incoming = self.plan.incoming.get(node.id, {})
        for spec in node.definition.connectable_params():
            if spec.name not in incoming:
                continue
            src_id, sock = incoming[spec.name]
            expr = exprs[(src_id, sock)]
            src_type = self.plan.nodes[src_id].definition.output(sock).type
            conv = conversion_between(src_type, spec.socket_type)
            if conv:
                expr = conv.template.format(expr)
            var = self.new_var(spec.name)
            lines.append(f"{var} = {spec.coerce_expr(expr)}")
            params[spec.name] = Expr(var)
        return params, lines

    # -- ensamblado --------------------------------------------------------------------

    def _main_function(
        self,
        body: list[str],
        pre: list[str],
        setup: list[str],
        cleanup: list[str],
        realtime: bool,
    ) -> list[str]:
        if realtime:
            signature = "def main(show: bool = True, max_frames: int = 0) -> None:"
            loop = ["frame_count = 0", "while True:", *_indent(body, 1)]
            loop += [
                "    frame_count += 1",
                "    if max_frames and frame_count >= max_frames:",
                "        break",
            ]
            if self.uses_display:
                loop += [
                    "    if show and cv2.waitKey(1) & 0xFF == ord('q'):",
                    "        break  # q cierra las ventanas",
                ]
            inner = setup + loop
        else:
            signature = "def main(show: bool = True) -> None:"
            inner = body

        main = [signature, "    node = 'inicio'", *_indent(pre, 1), "    try:", *_indent(inner, 2)]
        main += [
            "    except Exception as exc:",
            "        raise RuntimeError(f\"Error en el nodo '{node}': {exc}\") from exc",
        ]
        if realtime:
            final = list(cleanup)
            if self.uses_display:
                final += ["if show:", "    cv2.destroyAllWindows()"]
            main += ["    finally:", *_indent(final, 2)]
        elif self.uses_display:
            main += ["    if show:", "        cv2.waitKey(0)", "        cv2.destroyAllWindows()"]
        return main

    def _assemble(
        self,
        body: list[str],
        pre: list[str],
        setup: list[str],
        cleanup: list[str],
        realtime: bool,
    ) -> str:
        names = helpers.resolve(self._helpers)
        helper_src = "\n\n\n".join(helpers.HELPERS[n].source for n in names)
        code = "\n".join(self._main_function(body, pre, setup, cleanup, realtime))

        text = helper_src + "\n" + code
        imports = ["import sys"]
        if re.search(r"\bos\.", text):
            imports.append("import os")
        imports += ["", "import cv2"]
        if re.search(r"\bnp\.", text):
            imports.append("import numpy as np")

        version = f" {self.version}" if self.version else ""
        usage = "[--no-show]" + (" [--max-frames N]" if realtime else "")
        header = (
            "#!/usr/bin/env python3\n"
            f'"""Script generado por Palantir Nodes{version}.\n\n'
            "No necesita la aplicación; requiere: pip install opencv-python numpy\n"
            f"Uso: python este_script.py {usage}\n"
            '"""\n\n'
        )
        parts = [header + "\n".join(imports)]
        if helper_src:
            parts.append(helper_src)
        parts.append(code)
        parts.append(_MAIN_REALTIME if realtime else _MAIN_STATIC)
        return "\n\n\n".join(parts)
