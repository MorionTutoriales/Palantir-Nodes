"""Librería «Red (TCP)»: un servidor que recibe líneas de texto y un cliente que se conecta."""

from palantir_nodes.libraries import LibraryInfo
from palantir_nodes.libraries.tcp.nodes import TcpClient, TcpServer

LIBRARY = LibraryInfo(
    id="tcp",
    label="Red (TCP)",
    description=(
        "Comunicación por sockets TCP sin paquetes adicionales. «TCP Server» abre un servidor, "
        "recibe lo que le envían los clientes y puede enviarles datos; «TCP Client» se conecta a "
        "un servidor que esté escuchando. Cada línea (terminada en salto de línea) es un "
        "mensaje. Funcionan en tiempo real (F5), como los nodos WebSocket."
    ),
    nodes=(TcpServer, TcpClient),
)
