"""Reglas de conexión entre sockets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from palantir_nodes.core.topology import would_create_cycle
from palantir_nodes.core.types import conversion_between, is_compatible

if TYPE_CHECKING:
    from palantir_nodes.core.graph import Graph


@dataclass(frozen=True)
class ConnectionCheck:
    ok: bool
    reason: str = ""
    conversion: str | None = None

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class Endpoint:
    node_id: str
    socket: str
    is_output: bool


def _reject(reason: str) -> ConnectionCheck:
    return ConnectionCheck(False, reason)


def check_connection(
    graph: Graph,
    src_node: str,
    src_socket: str,
    dst_node: str,
    dst_socket: str,
    *,
    allow_replace: bool = True,
) -> ConnectionCheck:
    """Valida una conexión salida ``src`` -> entrada ``dst``.

    Con ``allow_replace`` una entrada ya conectada se considera válida, porque la nueva
    conexión sustituirá a la existente.
    """
    if src_node == dst_node:
        return _reject("Un nodo no puede conectarse consigo mismo")
    src = graph.nodes.get(src_node)
    dst = graph.nodes.get(dst_node)
    if src is None or dst is None:
        return _reject("El nodo no existe")
    if src.definition is None or dst.definition is None:
        return _reject("No se pueden conectar nodos de tipo desconocido")

    out_spec = src.definition.output(src_socket)
    if out_spec is None:
        if src.definition.input(src_socket) is not None:
            return _reject("No se pueden conectar dos entradas")
        return _reject(f"Salida inexistente: '{src_socket}'")
    in_spec = dst.definition.input(dst_socket)
    if in_spec is None:
        if dst.definition.output(dst_socket) is not None:
            return _reject("No se pueden conectar dos salidas")
        return _reject(f"Entrada inexistente: '{dst_socket}'")

    if not is_compatible(out_spec.type, in_spec.type):
        return _reject(f"Tipos incompatibles: {out_spec.type.value} → {in_spec.type.value}")

    existing = graph.link_to_input(dst_node, dst_socket)
    if existing is not None:
        if existing.src_node == src_node and existing.src_socket == src_socket:
            return _reject("La conexión ya existe")
        if not allow_replace:
            return _reject("La entrada ya tiene una conexión")

    if would_create_cycle(graph, src_node, dst_node):
        return _reject("La conexión crearía un ciclo")

    conversion = conversion_between(out_spec.type, in_spec.type)
    return ConnectionCheck(True, conversion=conversion.description if conversion else None)


def check_endpoints(
    graph: Graph, a: Endpoint, b: Endpoint, *, allow_replace: bool = True
) -> tuple[ConnectionCheck, Endpoint | None, Endpoint | None]:
    """Valida dos extremos en cualquier orden. Devuelve ``(check, salida, entrada)``."""
    if a.is_output == b.is_output:
        kind = "salidas" if a.is_output else "entradas"
        reason = f"No se pueden conectar dos {kind}"
        return _reject(reason), None, None
    src, dst = (a, b) if a.is_output else (b, a)
    check = check_connection(
        graph, src.node_id, src.socket, dst.node_id, dst.socket, allow_replace=allow_replace
    )
    return check, src, dst
