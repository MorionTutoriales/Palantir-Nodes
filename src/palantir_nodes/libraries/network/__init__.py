"""Librería «Red (WebSocket)»: un servidor que recibe datos y un cliente que se conecta a otro."""

from palantir_nodes.libraries import LibraryInfo, Requirement
from palantir_nodes.libraries.network.nodes import WebSocketClient, WebSocketServer

LIBRARY = LibraryInfo(
    id="network",
    label="Red (WebSocket)",
    description=(
        "Comunicación en tiempo real por WebSocket. «WebSocket Server» abre un servidor, recibe "
        "lo que le envían los clientes y puede enviarles datos; «WebSocket Client» se conecta a "
        "un servidor que esté escuchando. Funcionan en tiempo real (F5) y cada nodo mantiene el "
        "tiempo real activo mientras esté en el grafo."
    ),
    nodes=(WebSocketServer, WebSocketClient),
    requirements=(Requirement("websockets", "websockets"),),
)
