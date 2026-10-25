"""Servidor y cliente TCP para el grafo (se copia tal cual al script exportado).

TCP es un flujo de bytes, así que los mensajes se separan por saltos de línea: cada línea
recibida es un mensaje y cada mensaje enviado termina en un salto de línea (los saltos que el
propio texto contenga se envían como espacios). Solo usa la biblioteca estándar.
"""

from __future__ import annotations

import asyncio

from palantir_nodes.libraries.link import LinkBase


class TcpLink(LinkBase):
    """Servidor o cliente TCP con mensajes de una línea."""

    async def _serve(self) -> None:
        host, port = self.address
        server = await asyncio.start_server(self._handle, host, port)
        self._ready.set()
        async with server:
            await asyncio.Future()  # hasta que se cancele la tarea

    async def _keep_connected(self) -> None:
        host, port = self.address
        self._ready.set()
        while True:
            try:
                reader, writer = await asyncio.open_connection(host, port)
                try:
                    await self._listen(reader, writer, f"{host}:{port}")
                finally:
                    writer.close()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # sin servidor todavía: se reintenta
            await asyncio.sleep(1.0)

    async def _handle(self, reader, writer) -> None:
        peer = writer.get_extra_info("peername")
        try:
            await self._listen(reader, writer, f"{peer[0]}:{peer[1]}" if peer else "")
        finally:
            writer.close()

    async def _listen(self, reader, writer, sender: str) -> None:
        self._clients.add(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:  # el otro extremo cerró la conexión
                    break
                self._receive(line.decode("utf-8", "replace").rstrip("\r\n"), sender)
        finally:
            self._clients.discard(writer)

    async def _send_to(self, client, text: str) -> None:
        line = text.replace("\r", " ").replace("\n", " ") + "\n"
        client.write(line.encode("utf-8"))
        await client.drain()
