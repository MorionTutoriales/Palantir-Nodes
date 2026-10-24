"""Genera un script Python independiente a partir del plan de ejecución.

Usa el mismo ``ExecutionPlan`` y las mismas definiciones de nodo que el motor; cada
nodo aporta su fragmento con ``generate_code``.
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
from palantir_nodes.nodes.base import NodeDefinition

_RESERVED = (
    set(keyword.kwlist)
    | set(dir(builtins))
    | set(helpers.HELPERS)
    | {"cv2", "np", "os", "sys", "main", "show", "node", "exc"}
)


class ExportProblem(NamedTuple):
    node_id: str | None
    message: str


class ExportError(PalantirError):
    def __init__(self, problems: list[ExportProblem]) -> None:
        self.problems = problems
        super().__init__("\n".join(p.message for p in problems))


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
                        None, "El grafo no tiene nodos de salida (Image Viewer o Save Image)."
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
        for node_id in order:
            node = plan.nodes[node_id]
            definition = node.definition
            inputs = self._input_exprs(node, exprs)
            self._wanted = consumed[node_id]
            fragment = definition().generate_code(self, inputs, dict(node.params))
            for spec in definition.outputs:
                if spec.name in self._wanted:
                    exprs[(node_id, spec.name)] = fragment.outputs[spec.name]
            body += [f"# --- {definition.label} ---", f"node = {definition.label!r}"]
            body += fragment.lines + [""]
        return self._assemble(body)

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

    def _assemble(self, body: list[str]) -> str:
        names = helpers.resolve(self._helpers)
        helper_src = "\n\n\n".join(helpers.HELPERS[n].source for n in names)
        indented = [("        " + line) if line else "" for line in body]
        main = ["def main(show: bool = True) -> None:", "    node = 'inicio'", "    try:"]
        main += indented
        main += [
            "    except Exception as exc:",
            "        raise RuntimeError(f\"Error en el nodo '{node}': {exc}\") from exc",
        ]
        if self.uses_display:
            main += [
                "    if show:",
                "        cv2.waitKey(0)",
                "        cv2.destroyAllWindows()",
            ]
        code = "\n".join(main)
        text = helper_src + "\n" + code
        imports = ["import sys"]
        if re.search(r"\bos\.", text):
            imports.append("import os")
        imports.append("")
        imports.append("import cv2")
        if re.search(r"\bnp\.", text):
            imports.append("import numpy as np")
        version = f" {self.version}" if self.version else ""
        header = (
            "#!/usr/bin/env python3\n"
            f'"""Script generado por Palantir Nodes{version}.\n\n'
            "No necesita la aplicación; requiere: pip install opencv-python numpy\n"
            "Uso: python este_script.py [--no-show]\n"
            '"""\n\n'
        )
        parts = [header + "\n".join(imports)]
        if helper_src:
            parts.append(helper_src)
        parts.append(code)
        parts.append('if __name__ == "__main__":\n    main(show="--no-show" not in sys.argv[1:])\n')
        return "\n\n\n".join(parts)
