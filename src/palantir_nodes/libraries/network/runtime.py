"""Servidor y cliente WebSocket para el grafo (se copia tal cual al script exportado).

El paquete ``websockets`` se importa al arrancar, no al cargar este módulo.
"""

from __future__ import annotations

import asyncio

from palantir_nodes.libraries.link import MAX_PENDING, LinkBase  # noqa: F401


class WebSocketLink(LinkBase):
    """Servidor o cliente WebSocket; cada mensaje es un texto completo."""

    def _check_dependencies(self) -> None:
        try:
            import websockets.asyncio.client  # noqa: F401
            import websockets.asyncio.server  # noqa: F401
        except ImportError:
            raise ValueError(
                "Falta instalar el paquete 'websockets' 13 o superior (pip install -U websockets)"
            ) from None

    async def _serve(self) -> None:
        from websockets.asyncio.server import serve

        host, port = self.address
        async with serve(self._handle, host, port):
            self._ready.set()
            await asyncio.Future()  # hasta que se cancele la tarea

    async def _keep_connected(self) -> None:
        from websockets.asyncio.client import connect

        self._ready.set()
        while True:
            try:
                async with connect(self.address) as socket:
                    await self._listen(socket, self.address)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # sin servidor todavía: se reintenta
            await asyncio.sleep(1.0)

    async def _handle(self, socket) -> None:
        peer = socket.remote_address
        await self._listen(socket, f"{peer[0]}:{peer[1]}" if peer else "")

    async def _listen(self, socket, sender: str) -> None:
        self._clients.add(socket)
        try:
            async for message in socket:
                if isinstance(message, bytes):
                    message = message.decode("utf-8", "replace")
                self._receive(message, sender)
        finally:
            self._clients.discard(socket)

    async def _send_to(self, client, text: str) -> None:
        await client.send(text)
