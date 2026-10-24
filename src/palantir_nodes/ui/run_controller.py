"""Ejecución del grafo fuera del hilo de la interfaz.

El grafo se copia en un :class:`ExecutionPlan` en el hilo principal y el trabajo se hace
en un ``QThread`` propio. Si llegan peticiones mientras se procesa, se colapsan en una
sola: al terminar se ejecuta una última vez con el estado más reciente (nunca se
acumulan ejecuciones).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot

from palantir_nodes.core.graph import Graph, GraphEvent, GraphEventKind
from palantir_nodes.engine.executor import ExecContext, ExecutionResult, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.engine.realtime import source_nodes
from palantir_nodes.engine.thumbnails import PREVIEW_MAX
from palantir_nodes.ui.realtime_worker import RealtimeWorker

_TRIGGERS = {
    GraphEventKind.PARAM_CHANGED,
    GraphEventKind.INPUT_VALUE_CHANGED,
    GraphEventKind.LINK_ADDED,
    GraphEventKind.LINK_REMOVED,
    GraphEventKind.NODE_REMOVED,
    GraphEventKind.CLEARED,
}
DEBOUNCE_MS = 60


class _Worker(QObject):
    done = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._executor = Executor()

    @Slot(object, bool, object)
    def run(
        self, plan: ExecutionPlan, side_effects: bool, preview_max: tuple[int, int] | None
    ) -> None:
        try:
            ctx = ExecContext(side_effects=side_effects, preview_max=preview_max)
            result = self._executor.run(plan, ctx)
        except Exception as exc:  # fallo inesperado del motor: no debe matar el hilo
            result = ExecutionResult()
            result.errors["__engine__"] = f"Error interno del motor: {exc}"
        self.done.emit(result)

    @Slot()
    def clear_cache(self) -> None:
        self._executor.clear_cache()


class RunController(QObject):
    started = Signal()
    finished = Signal(object)  # ExecutionResult (estático o un fotograma en tiempo real)
    realtime_changed = Signal(bool)  # sesión en tiempo real iniciada / terminada
    realtime_stopped = Signal(str)  # motivo (vacío si la detuvo el usuario)

    _request = Signal(object, bool, object)
    _clear = Signal()

    def __init__(self, graph: Graph, parent=None) -> None:
        super().__init__(parent)
        self.graph = graph
        self.auto_run = True
        self._busy = False
        self._rerun: bool | None = None  # side_effects de la ejecución pendiente
        self._rt_worker: RealtimeWorker | None = None
        self._rt_thread: QThread | None = None
        self._rt_reason = ""
        self._paused = False
        self._preview_enabled = True

        self._thread = QThread(self)
        self._thread.setObjectName("palantir-engine")
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self._request.connect(self._worker.run)
        self._clear.connect(self._worker.clear_cache)
        self._worker.done.connect(self._on_done)
        self._thread.start()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._on_timer)
        graph.subscribe(self._on_graph_event)

    @property
    def busy(self) -> bool:
        return self._busy

    def _on_graph_event(self, event: GraphEvent) -> None:
        if self.auto_run and event.kind in _TRIGGERS:
            self._timer.start()

    def run(self, *, side_effects: bool = True) -> None:
        """Pide una ejecución. ``side_effects`` permite que Save Image escriba en disco."""
        self._timer.stop()
        if self.realtime_active:
            return  # en tiempo real los cambios llegan por update_plan
        if self._busy:
            self._rerun = bool(self._rerun) or side_effects
            return
        self._start(side_effects)

    def clear_cache(self) -> None:
        self._clear.emit()

    def _on_timer(self) -> None:
        if self._rt_worker is not None:
            self._rt_worker.update_plan(ExecutionPlan.from_graph(self.graph))
        else:
            self.run(side_effects=False)

    # -- tiempo real -------------------------------------------------------------------

    @property
    def realtime_active(self) -> bool:
        return self._rt_worker is not None

    @property
    def paused(self) -> bool:
        return self._paused

    def has_sources(self) -> bool:
        return bool(source_nodes(ExecutionPlan.from_graph(self.graph)))

    def start_realtime(self, *, side_effects: bool = True) -> bool:
        """Inicia el procesamiento continuo. ``False`` si ya hay una sesión o no hay fuentes."""
        if self._rt_worker is not None:
            return False
        plan = ExecutionPlan.from_graph(self.graph)
        if not source_nodes(plan):
            return False
        self._timer.stop()
        self._rt_reason = ""
        self._paused = False
        worker = RealtimeWorker(plan, side_effects, self._preview_max())
        thread = QThread()
        thread.setObjectName("palantir-realtime")
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.frame_ready.connect(self._on_frame)
        worker.done.connect(self._on_realtime_done)
        # Directa: ``quit`` es seguro entre hilos y no debe esperar al bucle de la interfaz
        # (que puede estar bloqueado en ``stop_realtime(wait=True)``).
        worker.done.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(self._cleanup_realtime)
        self._rt_worker, self._rt_thread = worker, thread
        thread.start()
        self.realtime_changed.emit(True)
        return True

    def stop_realtime(self, *, wait: bool = False) -> None:
        """Pide detener la sesión (``wait`` bloquea hasta liberar todos los recursos)."""
        if self._rt_worker is None:
            return
        thread = self._rt_thread
        self._rt_worker.request_stop()
        if wait and thread is not None:
            thread.wait()
            self._cleanup_realtime()

    # -- miniaturas --------------------------------------------------------------------

    @property
    def preview_enabled(self) -> bool:
        return self._preview_enabled

    def set_previews(self, enabled: bool) -> None:
        """Activa o desactiva el cálculo de miniaturas (también en una sesión en marcha)."""
        self._preview_enabled = enabled
        if self._rt_worker is not None:
            self._rt_worker.set_preview_max(self._preview_max())

    def _preview_max(self) -> tuple[int, int] | None:
        return PREVIEW_MAX if self._preview_enabled else None

    def set_paused(self, paused: bool) -> None:
        if self._rt_worker is not None:
            self._paused = paused
            self._rt_worker.set_paused(paused)

    @Slot()
    def _on_frame(self) -> None:
        if self._rt_worker is None:
            return
        result = self._rt_worker.take()
        if result is not None:
            self.finished.emit(result)

    @Slot(str)
    def _on_realtime_done(self, reason: str) -> None:
        self._rt_reason = reason

    @Slot()
    def _cleanup_realtime(self) -> None:
        worker, thread = self._rt_worker, self._rt_thread
        if worker is None:
            return
        self._rt_worker = self._rt_thread = None
        self._paused = False
        # Último fotograma pendiente antes de soltar el worker.
        result = worker.take()
        if result is not None:
            self.finished.emit(result)
        worker.deleteLater()
        if thread is not None:
            thread.deleteLater()
        self.realtime_changed.emit(False)
        self.realtime_stopped.emit(self._rt_reason)

    def _start(self, side_effects: bool) -> None:
        self._busy = True
        self.started.emit()
        self._request.emit(ExecutionPlan.from_graph(self.graph), side_effects, self._preview_max())

    @Slot(object)
    def _on_done(self, result: ExecutionResult) -> None:
        self._busy = False
        self.finished.emit(result)
        if self._rerun is not None:
            side_effects, self._rerun = self._rerun, None
            self._start(side_effects)

    def shutdown(self) -> None:
        self._timer.stop()
        self._rerun = None
        self.stop_realtime(wait=True)
        self._thread.quit()
        self._thread.wait()
