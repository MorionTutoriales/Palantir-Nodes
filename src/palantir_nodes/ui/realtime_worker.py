"""Bucle de tiempo real en un hilo propio.

El bucle nunca acumula fotogramas: cada resultado nuevo reemplaza al anterior que la
interfaz aún no haya recogido, y solo se avisa a la interfaz una vez por cada recogida.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal, Slot

from palantir_nodes.engine.executor import ExecutionResult
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.engine.realtime import RealtimeSession

_FPS_SMOOTHING = 0.9


class RealtimeWorker(QObject):
    frame_ready = Signal()
    done = Signal(str)  # motivo de finalización ("" si el usuario la detuvo)

    def __init__(
        self,
        plan: ExecutionPlan,
        side_effects: bool,
        preview_max: tuple[int, int] | None = None,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._preview_max = preview_max
        self._side_effects = side_effects
        self._lock = threading.Lock()
        self._new_plan: ExecutionPlan | None = None
        self._latest: ExecutionResult | None = None
        self._notified = False
        self._stop = threading.Event()
        self._running = threading.Event()
        self._running.set()

    # -- llamadas desde el hilo de la interfaz -----------------------------------------

    def request_stop(self) -> None:
        self._stop.set()
        self._running.set()  # despierta la pausa para poder salir

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._running.clear()
        else:
            self._running.set()

    def set_preview_max(self, preview_max: tuple[int, int] | None) -> None:
        self._preview_max = preview_max  # asignación atómica; la lee el bucle en cada vuelta

    def update_plan(self, plan: ExecutionPlan) -> None:
        with self._lock:
            self._new_plan = plan

    def take(self) -> ExecutionResult | None:
        """Recoge el último resultado (y rearma el aviso)."""
        with self._lock:
            result, self._latest = self._latest, None
            self._notified = False
        return result

    # -- hilo de trabajo ---------------------------------------------------------------

    def _publish(self, result: ExecutionResult) -> None:
        with self._lock:
            previous = self._latest
            if result.previews is None and previous is not None:
                result.previews = previous.previews  # no perder miniaturas al sustituir
            self._latest = result  # sustituye a un resultado no recogido
            notify = not self._notified
            self._notified = True
        if notify:
            self.frame_ready.emit()

    @Slot()
    def run(self) -> None:
        reason = ""
        session: RealtimeSession | None = None
        try:
            session = RealtimeSession(self._plan, side_effects=self._side_effects)
            smoothed: float | None = None
            last = time.perf_counter()
            while not self._stop.is_set():
                if not self._running.is_set():
                    self._running.wait(0.05)
                    last = time.perf_counter()
                    continue
                with self._lock:
                    plan, self._new_plan = self._new_plan, None
                if plan is not None:
                    session.set_plan(plan)

                session.preview_size = self._preview_max
                started = time.perf_counter()
                result = session.step()
                if result is None:
                    reason = session.finish_reason
                    break
                interval = session.target_interval
                spent = time.perf_counter() - started
                if interval and spent < interval:
                    self._stop.wait(interval - spent)  # respeta el ritmo del archivo

                now = time.perf_counter()
                loop_time, last = now - last, now
                smoothed = (
                    loop_time
                    if smoothed is None
                    else _FPS_SMOOTHING * smoothed + (1 - _FPS_SMOOTHING) * loop_time
                )
                result.fps = 1.0 / smoothed if smoothed > 0 else None
                self._publish(result)
        except Exception as exc:  # fallo inesperado: se informa y se liberan los recursos
            reason = f"Error interno: {exc}"
        finally:
            if session is not None:
                session.close()
            self.done.emit(reason)
