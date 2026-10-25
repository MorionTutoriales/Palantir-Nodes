"""Reloj que avisa cada cierto tiempo (lo usan el nodo Tick y el script exportado)."""

from __future__ import annotations

import time


class TickClock:
    """Fuente de tiempo: ``read()`` devuelve ``(tick, cuenta, segundos)`` en cada fotograma.

    ``tick`` es verdadero solo en el fotograma en que se cumple un intervalo. Si el
    procesamiento va más lento que el intervalo no se disparan avisos atrasados en ráfaga:
    se avisa una vez y se sigue desde el instante actual.
    """

    fps = 60.0  # ritmo máximo de fotogramas cuando el grafo incluye un Tick

    def __init__(self, interval: float, at_start: bool = True) -> None:
        self.interval = max(float(interval), 0.001)
        self.count = 0
        self._start = time.perf_counter()
        self._next = 0.0 if at_start else self.interval

    def read(self) -> tuple[bool, int, float]:
        elapsed = time.perf_counter() - self._start
        tick = elapsed >= self._next
        if tick:
            self.count += 1
            self._next += self.interval * (int((elapsed - self._next) // self.interval) + 1)
        return tick, self.count, elapsed

    def release(self) -> None:
        pass
