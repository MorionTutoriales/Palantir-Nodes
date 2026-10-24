"""Instantánea inmutable del grafo para ejecutarla sin tocar el modelo vivo.

Se crea en el hilo de la interfaz y se entrega al hilo de trabajo, de modo que el
usuario puede seguir editando mientras se procesa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from palantir_nodes.core.graph import Graph
from palantir_nodes.core.topology import topological_order
from palantir_nodes.nodes.base import NodeDefinition


@dataclass(frozen=True)
class PlanNode:
    id: str
    definition: type[NodeDefinition]
    params: dict[str, Any]
    input_values: dict[str, Any]


@dataclass
class ExecutionPlan:
    order: list[str] = field(default_factory=list)
    nodes: dict[str, PlanNode] = field(default_factory=dict)
    # nodo destino -> {entrada: (nodo origen, salida)}
    incoming: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def from_graph(cls, graph: Graph) -> ExecutionPlan:
        plan = cls(order=topological_order(graph))
        for node_id, node in graph.nodes.items():
            plan.nodes[node_id] = PlanNode(
                node_id, node.definition, dict(node.params), dict(node.input_values)
            )
        for link in graph.links.values():
            plan.incoming.setdefault(link.dst_node, {})[link.dst_socket] = (
                link.src_node,
                link.src_socket,
            )
        return plan
