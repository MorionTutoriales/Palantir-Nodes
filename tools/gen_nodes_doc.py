"""Genera docs/nodos.md: el catálogo de nodos, leído del propio registro (siempre al día).

Uso (desde la raíz del proyecto):

    .venv\\Scripts\\python tools\\gen_nodes_doc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from palantir_nodes.libraries import available_libraries
from palantir_nodes.nodes.base import NodeDefinition
from palantir_nodes.nodes.registry import load_builtin_nodes

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "nodos.md"


def sockets(specs) -> str:
    return ", ".join(f"`{s.display_label}` ({s.type.value})" for s in specs) or "—"


def params(definition: type[NodeDefinition]) -> str:
    return ", ".join(p.display_label for p in definition.params) or "—"


def table(nodes: list[type[NodeDefinition]]) -> list[str]:
    lines = [
        "| Nodo | Qué hace | Entradas | Salidas | Parámetros |",
        "|---|---|---|---|---|",
    ]
    for node in nodes:
        description = node.description.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| **{node.label}** | {description} | {sockets(node.inputs)} "
            f"| {sockets(node.outputs)} | {params(node)} |"
        )
    return lines


def main() -> None:
    registry = load_builtin_nodes()
    groups = registry.by_category()
    total = sum(len(nodes) for nodes in groups.values())
    out = [
        "# Catálogo de nodos",
        "",
        f"La aplicación incluye **{total} nodos** en {len(groups)} categorías, más los de las "
        "[librerías opcionales](#librerías-opcionales). Esta página se genera con "
        "`tools/gen_nodes_doc.py` a partir del propio registro de nodos.",
        "",
        "Los tipos de socket son: `Image`, `Float`, `Integer`, `Boolean`, `String`, `Color`, "
        "`Vector2`, `Vector3` y `Any`. Un decimal se puede conectar a un entero (se redondea), un "
        "entero o booleano a un decimal, y `Any` acepta cualquier valor. Los parámetros "
        "numéricos, booleanos, de color y de vector tienen además su propio socket de entrada "
        "para alimentarlos desde otro nodo.",
        "",
    ]
    for category, nodes in groups.items():
        out += [f"## {category}", "", *table(nodes), ""]
    out += ["## Librerías opcionales", ""]
    out += [
        "Se activan por proyecto en **Nodos → Librerías del proyecto…** y sus nodos aparecen "
        "entonces en el menú de añadir.",
        "",
    ]
    for library in available_libraries():
        needs = ", ".join(f"`{r.package}`" for r in library.requirements) or "nada (solo Python)"
        out += [f"### {library.label}", "", library.description, "", f"Necesita: {needs}.", ""]
        out += [*table(list(library.nodes)), ""]
    OUTPUT.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"escrito {OUTPUT} ({total} nodos integrados)", file=sys.stderr)


if __name__ == "__main__":
    main()
