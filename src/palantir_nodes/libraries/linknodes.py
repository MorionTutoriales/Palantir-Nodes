"""Base de los nodos de conexión de red (WebSocket y TCP): una fuente que recibe y envía texto.

No se registran solos: los añade el gestor de librerías.
"""

from __future__ import annotations

from typing import Any

from palantir_nodes.core.types import SocketType as T
from palantir_nodes.nodes.base import CodeFragment, NodeDefinition
from palantir_nodes.nodes.categories import register_category
from palantir_nodes.nodes.specs import InputSpec, ParamKind, ParamSpec

NETWORK = "Red"
register_category(NETWORK, "#4B7F52", 35)

POLICY = ParamSpec(
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


class LinkNode(NodeDefinition):
    """Nodo fuente sobre una conexión (``link_class``) que recibe y puede enviar texto."""

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
    link_class: type  # clase de la conexión (``LinkBase``)
    helper = ""  # nombre del helper del script exportado (la clase de la conexión)
    requirement = ""  # paquete de pip que necesita el script exportado, si hay alguno

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
    def open_source(cls, params: dict[str, Any]):
        return cls.link_class(cls.mode, cls.address(params), params["policy"]).start()

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
        gen.helper(self.helper)
        gen.add_import("import asyncio")
        gen.add_import("import threading")
        if self.requirement:
            gen.add_requirement(self.requirement)
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
                f"{link} = {self.helper}({self.mode!r}, {self.address(params)!r}, "
                f"{params['policy']!r}).start()"
            ],
            cleanup=[f"if {link} is not None:", f"    {link}.stop()"],
        )


class ServerOutputs:
    """Salidas y forma de los datos de un servidor (clientes, mensaje, nuevo, origen)."""

    @staticmethod
    def shape(connections, message, new, sender):
        return {"clients": connections, "message": message, "new_message": new, "sender": sender}

    @staticmethod
    def shape_code(conn, message, new, sender):
        return {"clients": conn, "message": message, "new_message": new, "sender": sender}


class ClientOutputs:
    """Salidas y forma de los datos de un cliente (conectado, mensaje, nuevo)."""

    @staticmethod
    def shape(connections, message, new, sender):
        return {"connected": connections > 0, "message": message, "new_message": new}

    @staticmethod
    def shape_code(conn, message, new, sender):
        return {"connected": f"({conn} > 0)", "message": message, "new_message": new}
