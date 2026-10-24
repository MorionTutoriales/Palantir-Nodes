"""Ejecución del grafo fuera del hilo de la interfaz.

El grafo se copia en un :class:`ExecutionPlan` en el hilo principal y el trabajo se hace
en un ``QThread`` propio. Si llegan peticiones mientras se procesa, se colapsan en una
sola: al terminar se ejecuta una última vez con el estado más reciente (nunca se
acumulan ejecuciones).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from palantir_nodes.core.graph import Graph, GraphEvent, GraphEventKind
from palantir_nodes.engine.executor import ExecContext, ExecutionResult, Executor
from palantir_nodes.engine.plan import ExecutionPlan

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

    @Slot(object, bool)
    def run(self, plan: ExecutionPlan, side_effects: bool) -> None:
        try:
            result = self._executor.run(plan, ExecContext(side_effects=side_effects))
        except Exception as exc:  # fallo inesperado del motor: no debe matar el hilo
            result = ExecutionResult()
            result.errors["__engine__"] = f"Error interno del motor: {exc}"
        self.done.emit(result)

    @Slot()
    def clear_cache(self) -> None:
        self._executor.clear_cache()


class RunController(QObject):
    started = Signal()
    finished = Signal(object)  # ExecutionResult

    _request = Signal(object, bool)
    _clear = Signal()

    def __init__(self, graph: Graph, parent=None) -> None:
        super().__init__(parent)
        self.graph = graph
        self.auto_run = True
        self._busy = False
        self._rerun: bool | None = None  # side_effects de la ejecución pendiente

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
        self._timer.timeout.connect(lambda: self.run(side_effects=False))
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
        if self._busy:
            self._rerun = bool(self._rerun) or side_effects
            return
        self._start(side_effects)

    def clear_cache(self) -> None:
        self._clear.emit()

    def _start(self, side_effects: bool) -> None:
        self._busy = True
        self.started.emit()
        self._request.emit(ExecutionPlan.from_graph(self.graph), side_effects)

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
        self._thread.quit()
        self._thread.wait()
