"""Base común de las conexiones de red del grafo (se copia tal cual al script exportado).

Una conexión corre un bucle de asyncio en un hilo propio y se maneja desde el hilo del grafo
con llamadas que no bloquean: ``read()`` entrega lo recibido y ``send()`` encola el envío.
Cada protocolo (WebSocket, TCP) solo aporta cómo escuchar, conectar y enviar.
"""

from __future__ import annotations

import asyncio
import threading

# Mensajes recibidos que se conservan como máximo (los más antiguos se descartan).
MAX_PENDING = 1000


class LinkBase:
    """Servidor (``mode="server"``) o cliente (``mode="client"``) en un hilo propio.

    - Servidor: ``address`` es ``(host, puerto)``; acepta cualquier número de clientes.
    - Cliente: ``address`` es a dónde conectarse; reintenta cada segundo si se cae.
    - ``policy``: ``"latest"`` entrega solo el último mensaje recibido desde la lectura
      anterior; ``"queue"`` entrega uno por lectura, en orden.
    """

    fps = 60.0  # ritmo máximo de fotogramas cuando el grafo incluye una conexión

    def __init__(self, mode: str, address, policy: str = "latest") -> None:
        self.mode = mode
        self.address = address
        self.policy = policy
        self._inbox: list[tuple[str, str]] = []
        self._last = ""
        self._sender = ""
        self._lock = threading.Lock()
        self._clients: set = set()
        self._loop = None
        self._task = None
        self._thread = None
        self._ready = threading.Event()
        self._error = ""

    # -- a cargo de cada protocolo --------------------------------------------------------

    def _check_dependencies(self) -> None:
        """Lanza ``ValueError`` si falta algún paquete necesario."""

    async def _serve(self) -> None:
        raise NotImplementedError

    async def _keep_connected(self) -> None:
        raise NotImplementedError

    async def _send_to(self, client, text: str) -> None:
        raise NotImplementedError

    # -- ciclo de vida ------------------------------------------------------------------

    def start(self):
        self._check_dependencies()
        self._thread = threading.Thread(target=self._run, name="network-link", daemon=True)
        self._thread.start()
        if not self._ready.wait(5.0):
            self.stop()
            raise ValueError("La conexión no arrancó a tiempo")
        if self._error:
            self.stop()
            raise ValueError(self._error)
        return self

    def stop(self) -> None:
        loop, task = self._loop, self._task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:  # el bucle ya terminó
                pass
        if self._thread is not None:
            self._thread.join(3.0)
            self._thread = None

    release = stop  # así se comporta como una fuente de fotogramas

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as exc:
            self._error = self._error or str(exc)
        finally:
            self._ready.set()

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        try:
            if self.mode == "server":
                await self._serve()
            else:
                await self._keep_connected()
        except asyncio.CancelledError:
            pass
        except OSError as exc:
            self._error = f"No se pudo abrir {self.address[0]}:{self.address[1]}: {exc}"
        finally:
            self._ready.set()

    def _receive(self, message: str, sender: str) -> None:
        with self._lock:
            self._inbox.append((message, sender))
            if len(self._inbox) > MAX_PENDING:
                del self._inbox[0]

    # -- uso desde el grafo ---------------------------------------------------------------

    def read(self) -> tuple[int, str, bool, str]:
        """``(conexiones, mensaje, nuevo, emisor)``: ``nuevo`` solo si llegó algo desde la
        lectura anterior; si no, ``mensaje`` conserva el último recibido."""
        with self._lock:
            new = bool(self._inbox)
            if new:
                if self.policy == "queue":
                    self._last, self._sender = self._inbox.pop(0)
                else:
                    self._last, self._sender = self._inbox[-1]
                    self._inbox.clear()
            return len(self._clients), self._last, new, self._sender

    def send(self, text: str) -> None:
        """Envía ``text`` a todos los conectados (sin esperar a que termine el envío)."""
        loop = self._loop
        if loop is None or not self._clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(str(text)), loop)
        except RuntimeError:  # el bucle ya terminó
            pass

    async def _broadcast(self, text: str) -> None:
        for client in list(self._clients):
            try:
                await self._send_to(client, text)
            except Exception:
                pass  # ese cliente se cayó: su escucha lo quitará
