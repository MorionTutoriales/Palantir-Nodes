"""Nodos de la librería TCP. No se registran solos: los añade el gestor de librerías."""

from __future__ import annotations

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.libraries.linknodes import POLICY, ClientOutputs, LinkNode, ServerOutputs
from palantir_nodes.libraries.tcp.runtime import TcpLink
from palantir_nodes.nodes.specs import OutputSpec, ParamKind, ParamSpec

_HOST = ParamSpec("host", ParamKind.STRING, "127.0.0.1", label="Dirección", connectable=False)
_PORT = ParamSpec(
    "port", ParamKind.INT, 9000, label="Puerto", minimum=1, maximum=65535, connectable=False
)


class TcpServer(ServerOutputs, LinkNode):
    type_id = "net.tcp_server"
    label = "TCP Server"
    description = (
        "Abre un servidor TCP y recibe lo que le envíen los clientes: cada línea es un mensaje. "
        "Con «Enviar» y «Mensaje» conectados, manda ese texto (terminado en salto de línea) a "
        "todos los clientes. Usa 0.0.0.0 como dirección para aceptar conexiones de otros equipos."
    )
    mode = "server"
    link_class = TcpLink
    helper = "TcpLink"
    outputs = (
        OutputSpec("clients", T.INTEGER, "Clientes"),
        OutputSpec("message", T.STRING, "Mensaje"),
        OutputSpec("new_message", T.BOOLEAN, "Mensaje nuevo"),
        OutputSpec("sender", T.STRING, "Origen"),
    )
    params = (_HOST, _PORT, POLICY)

    @classmethod
    def address(cls, params):
        return (params["host"], int(params["port"]))

    @classmethod
    def export_problems(cls, params):
        return [] if params["host"].strip() else ["falta la dirección del servidor"]


class TcpClient(ClientOutputs, LinkNode):
    type_id = "net.tcp_client"
    label = "TCP Client"
    description = (
        "Se conecta a un servidor TCP que esté escuchando (reintenta cada segundo si no está o "
        "se cae). Cada línea que recibe es un mensaje; puede enviarle texto con «Enviar» y "
        "«Mensaje»."
    )
    mode = "client"
    link_class = TcpLink
    helper = "TcpLink"
    outputs = (
        OutputSpec("connected", T.BOOLEAN, "Conectado"),
        OutputSpec("message", T.STRING, "Mensaje"),
        OutputSpec("new_message", T.BOOLEAN, "Mensaje nuevo"),
    )
    params = (_HOST, _PORT, POLICY)

    @classmethod
    def address(cls, params):
        return (params["host"].strip(), int(params["port"]))

    @classmethod
    def export_problems(cls, params):
        return [] if params["host"].strip() else ["falta la dirección del servidor"]
