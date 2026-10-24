"""Análisis de dependencias: orden topológico, ciclos y nodos afectados."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from palantir_nodes.core.errors import CycleError

if TYPE_CHECKING:
    from palantir_nodes.core.graph import Graph


def _successors(graph: Graph) -> dict[str, set[str]]:
    succ: dict[str, set[str]] = {node_id: set() for node_id in graph.nodes}
    for link in graph.links.values():
        succ[link.src_node].add(link.dst_node)
    return succ


def _predecessors(graph: Graph) -> dict[str, set[str]]:
    pred: dict[str, set[str]] = {node_id: set() for node_id in graph.nodes}
    for link in graph.links.values():
        pred[link.dst_node].add(link.src_node)
    return pred


def _reachable(adjacency: dict[str, set[str]], start: str) -> set[str]:
    seen: set[str] = set()
    stack = list(adjacency.get(start, ()))
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        stack.extend(adjacency.get(node_id, ()))
    return seen


def downstream_nodes(graph: Graph, node_id: str) -> set[str]:
    """Nodos que dependen (directa o indirectamente) de ``node_id``, sin incluirlo."""
    return _reachable(_successors(graph), node_id)


def upstream_nodes(graph: Graph, node_id: str) -> set[str]:
    """Nodos de los que depende ``node_id``, sin incluirlo."""
    return _reachable(_predecessors(graph), node_id)


def would_create_cycle(graph: Graph, src_node: str, dst_node: str) -> bool:
    """Indica si añadir la arista ``src_node -> dst_node`` crearía un ciclo."""
    return src_node == dst_node or src_node in downstream_nodes(graph, dst_node)


def topological_order(graph: Graph) -> list[str]:
    """Orden de ejecución de los nodos (algoritmo de Kahn, estable por orden de inserción).

    Lanza :class:`CycleError` si el grafo contiene un ciclo.
    """
    succ = _successors(graph)
    in_degree = {node_id: 0 for node_id in graph.nodes}
    for targets in succ.values():
        for target in targets:
            in_degree[target] += 1

    position = {node_id: i for i, node_id in enumerate(graph.nodes)}
    ready = deque(node_id for node_id in graph.nodes if in_degree[node_id] == 0)
    order: list[str] = []
    while ready:
        node_id = ready.popleft()
        order.append(node_id)
        for target in sorted(succ[node_id], key=position.__getitem__):
            in_degree[target] -= 1
            if in_degree[target] == 0:
                ready.append(target)

    if len(order) != len(graph.nodes):
        raise CycleError("El grafo contiene un ciclo de dependencias")
    return order
