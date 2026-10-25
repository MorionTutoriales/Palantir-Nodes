"""Nodos de la librería de red. No se registran solos: los añade el gestor de librerías."""

from __future__ import annotations

from typing import Any

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.libraries.network.runtime import WebSocketLink
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import register_category
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec

NETWORK = "Red"
register_category(NETWORK, "#4B7F52", 35)

_POLICY = ParamSpec(
    "policy",
    ParamKind.ENUM,
    "latest",
    label="Mensajes",
    options=(
        ("latest", "Solo el último"),
        ("queue", "Todos, uno por fotograma"),
    ),
    connectable=False,
    tooltip=(
        "Si llegan varios mensajes entre dos fotogramas: entregar solo el último o ir "
        "entregándolos en orden, uno en cada fotograma."
    ),
)


class _LinkNode(NodeDefinition):
    """Base de los nodos de red: una fuente que recibe y puede enviar texto."""

    category = NETWORK
    is_source = True
    cacheable = False
    inputs = (
        InputSpec(
            "send",
            T.BOOLEAN,
            "Enviar",
            default=True,
            tooltip="Se envía el mensaje en cada fotograma en que esto sea verdadero",
        ),
        InputSpec("message", T.STRING, "Mensaje", optional=True),
    )
    mode = "server"

    # -- por cada tipo de nodo --------------------------------------------------------

    @classmethod
    def address(cls, params: dict[str, Any]):
        raise NotImplementedError

    @staticmethod
    def shape(connections: int, message: str, new: bool, sender: str) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def shape_code(conn: str, message: str, new: str, sender: str) -> dict[str, str]:
        raise NotImplementedError

    # -- común ------------------------------------------------------------------------

    @classmethod
    def open_source(cls, params: dict[str, Any]) -> WebSocketLink:
        return WebSocketLink(cls.mode, cls.address(params), params["policy"]).start()

    def process(self, ctx, inputs, params):
        state = ctx.frames.get(ctx.node_id)
        if state is None:  # ejecución estática: no hay conexión abierta
            return self.shape(0, "", False, "")
        text = inputs["message"]
        link = ctx.sources.get(ctx.node_id)
        if link is not None and ctx.side_effects and inputs["send"] and text not in (None, ""):
            link.send(text)
        return self.shape(*state)

    def generate_code(self, gen, inputs, params):
        gen.helper("WebSocketLink")
        gen.add_import("import asyncio")
        gen.add_import("import threading")
        gen.add_requirement("websockets")
        link = gen.new_var("link")
        conn, message, new, sender = (
            gen.new_var(n) for n in ("connections", "received", "new_message", "sender")
        )
        text = inputs["message"]
        lines = [
            f"{conn}, {message}, {new}, {sender} = {link}.read()",
            f"if {inputs['send']} and {text} is not None and {text} != '':",
            f"    {link}.send({text})",
            "time.sleep(0.001)  # cede la CPU entre fotogramas",
        ]
        return CodeFragment(
            lines,
            self.shape_code(conn, message, new, sender),
            pre=[f"{link} = None"],
            setup=[
                f"{link} = WebSocketLink({self.mode!r}, {self.address(params)!r}, "
                f"{params['policy']!r}).start()"
            ],
            cleanup=[f"if {link} is not None:", f"    {link}.stop()"],
        )


class WebSocketServer(_LinkNode):
    type_id = "net.ws_server"
    label = "WebSocket Server"
    description = (
        "Abre un servidor WebSocket y recibe lo que le envíen los clientes. Con «Enviar» y "
        "«Mensaje» conectados, manda ese texto a todos los clientes. Usa 0.0.0.0 como "
        "dirección para aceptar conexiones desde otros equipos."
    )
    mode = "server"
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
        _POLICY,
    )

    @classmethod
    def address(cls, params):
        return (params["host"], int(params["port"]))

    @staticmethod
    def shape(connections, message, new, sender):
        return {"clients": connections, "message": message, "new_message": new, "sender": sender}

    @staticmethod
    def shape_code(conn, message, new, sender):
        return {"clients": conn, "message": message, "new_message": new, "sender": sender}

    @classmethod
    def export_problems(cls, params):
        return [] if params["host"].strip() else ["falta la dirección del servidor"]


class WebSocketClient(_LinkNode):
    type_id = "net.ws_client"
    label = "WebSocket Client"
    description = (
        "Se conecta a un servidor WebSocket que esté escuchando (reintenta cada segundo si no "
        "está o se cae). Recibe sus mensajes y puede enviarle texto con «Enviar» y «Mensaje»."
    )
    mode = "client"
    outputs = (
        OutputSpec("connected", T.BOOLEAN, "Conectado"),
        OutputSpec("message", T.STRING, "Mensaje"),
        OutputSpec("new_message", T.BOOLEAN, "Mensaje nuevo"),
    )
    params = (
        ParamSpec(
            "url", ParamKind.STRING, "ws://127.0.0.1:8765", label="Dirección", connectable=False
        ),
        _POLICY,
    )

    @classmethod
    def address(cls, params):
        return params["url"].strip()

    @staticmethod
    def shape(connections, message, new, sender):
        return {"connected": connections > 0, "message": message, "new_message": new}

    @staticmethod
    def shape_code(conn, message, new, sender):
        return {"connected": f"({conn} > 0)", "message": message, "new_message": new}

    @classmethod
    def export_problems(cls, params):
        if params["url"].strip().startswith(("ws://", "wss://")):
            return []
        return ["la dirección debe empezar por ws:// o wss://"]
