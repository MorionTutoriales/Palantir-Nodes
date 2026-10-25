"""Nodos de la librería WebSocket. No se registran solos: los añade el gestor de librerías."""

from __future__ import annotations

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.libraries.linknodes import POLICY, ClientOutputs, LinkNode, ServerOutputs
from palantir_nodes.libraries.network.runtime import WebSocketLink
from palantir_nodes.nodes.specs import OutputSpec, ParamKind, ParamSpec


class WebSocketServer(ServerOutputs, LinkNode):
    type_id = "net.ws_server"
    label = "WebSocket Server"
    description = (
        "Abre un servidor WebSocket y recibe lo que le envíen los clientes. Con «Enviar» y "
        "«Mensaje» conectados, manda ese texto a todos los clientes. Usa 0.0.0.0 como "
        "dirección para aceptar conexiones desde otros equipos."
    )
    mode = "server"
    link_class = WebSocketLink
    helper = "WebSocketLink"
    requirement = "websockets"
    outputs = (
        OutputSpec("clients", T.INTEGER, "Clientes"),
        OutputSpec("message", T.STRING, "Mensaje"),
        OutputSpec("new_message", T.BOOLEAN, "Mensaje nuevo"),
        OutputSpec("sender", T.STRING, "Origen"),
    )
    params = (
        ParamSpec("host", ParamKind.STRING, "127.0.0.1", label="Dirección", connectable=False),
        ParamSpec(
            "port", ParamKind.INT, 8765, label="Puerto", minimum=1, maximum=65535, connectable=False
        ),
        POLICY,
    )

    @classmethod
    def address(cls, params):
        return (params["host"], int(params["port"]))

    @classmethod
    def export_problems(cls, params):
        return [] if params["host"].strip() else ["falta la dirección del servidor"]


class WebSocketClient(ClientOutputs, LinkNode):
    type_id = "net.ws_client"
    label = "WebSocket Client"
    description = (
        "Se conecta a un servidor WebSocket que esté escuchando (reintenta cada segundo si no "
        "está o se cae). Recibe sus mensajes y puede enviarle texto con «Enviar» y «Mensaje»."
    )
    mode = "client"
    link_class = WebSocketLink
    helper = "WebSocketLink"
    requirement = "websockets"
    outputs = (
        OutputSpec("connected", T.BOOLEAN, "Conectado"),
        OutputSpec("message", T.STRING, "Mensaje"),
        OutputSpec("new_message", T.BOOLEAN, "Mensaje nuevo"),
    )
    params = (
        ParamSpec(
            "url", ParamKind.STRING, "ws://127.0.0.1:8765", label="Dirección", connectable=False
        ),
        POLICY,
    )

    @classmethod
    def address(cls, params):
        return params["url"].strip()

    @classmethod
    def export_problems(cls, params):
        if params["url"].strip().startswith(("ws://", "wss://")):
            return []
        return ["la dirección debe empezar por ws:// o wss://"]
