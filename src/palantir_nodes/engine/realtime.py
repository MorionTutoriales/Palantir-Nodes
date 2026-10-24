"""Procesamiento continuo de fotogramas (video y cámaras). No depende de Qt.

Una :class:`RealtimeSession` abre las fuentes del grafo, avanza un fotograma por llamada a
``step()`` y libera todos los recursos en ``close()``. Es síncrona: el hilo que la use
decide el ritmo (ver ``ui/run_controller.py``).
"""

from __future__ import annotations

from typing import Any

from palantir_nodes.engine.executor import ExecContext, ExecutionResult, Executor
from palantir_nodes.engine.plan import ExecutionPlan


def source_nodes(plan: ExecutionPlan) -> list[str]:
    return [i for i in plan.order if plan.nodes[i].definition.is_source]


class RealtimeSession:
    def __init__(self, plan: ExecutionPlan, *, side_effects: bool = True) -> None:
        self.plan = plan
        self.ctx = ExecContext(side_effects=side_effects, realtime=True)
        self.executor = Executor()
        self.finished = False
        self.finish_reason = ""
        self._sources: dict[str, tuple[Any, Any]] = {}  # nodo -> (configuración, fuente)
        self._errors: dict[str, str] = {}
        self._reconcile()

    # -- fuentes -----------------------------------------------------------------------

    def _config(self, node_id: str) -> tuple:
        node = self.plan.nodes[node_id]
        return (node.definition.type_id, tuple(sorted(node.params.items())))

    def _reconcile(self) -> None:
        wanted = set(source_nodes(self.plan))
        for node_id in list(self._sources):
            if node_id not in wanted or self._sources[node_id][0] != self._config(node_id):
                self._sources.pop(node_id)[1].release()
        for node_id in list(self._errors):
            if node_id not in wanted:
                del self._errors[node_id]
        for node_id in wanted:
            config = self._config(node_id)
            if node_id in self._sources:
                continue
            if node_id in self._errors and self._errors[node_id][0] == config:
                continue
            try:
                source = self.plan.nodes[node_id].definition.open_source(
                    dict(self.plan.nodes[node_id].params)
                )
            except Exception as exc:  # no se pudo abrir: el nodo muestra el motivo
                self._errors[node_id] = (config, str(exc))
            else:
                self._sources[node_id] = (config, source)
                self._errors.pop(node_id, None)

    def set_plan(self, plan: ExecutionPlan) -> None:
        """Aplica un grafo modificado sin reiniciar las fuentes que no cambiaron."""
        self.plan = plan
        self._reconcile()

    @property
    def target_interval(self) -> float | None:
        """Segundos entre fotogramas si hay archivos de video (``None`` = sin ritmo fijo)."""
        rates = [s.fps for _, s in self._sources.values() if getattr(s, "fps", None)]
        return 1.0 / min(rates) if rates else None

    # -- ejecución ---------------------------------------------------------------------

    def step(self) -> ExecutionResult | None:
        """Procesa el siguiente fotograma. ``None`` si la sesión terminó (ver ``finish_reason``)."""
        if self.finished:
            return None
        frames: dict[str, Any] = {}
        for node_id, (_config, source) in self._sources.items():
            frame = source.read()
            if frame is None:
                self.finished = True
                label = self.plan.nodes[node_id].definition.label
                self.finish_reason = f"'{label}' terminó"
                return None
            frames[node_id] = frame

        self.ctx.frames = frames
        self.ctx.frame_index += 1
        result = self.executor.run(self.plan, self.ctx)
        for node_id, (_config, message) in self._errors.items():
            result.errors[node_id] = message
            result.blocked.pop(node_id, None)

        if not self._sources:  # nada que reproducir: un único resultado con los errores
            self.finished = True
            first = next(iter(self._errors.values()), None)
            self.finish_reason = first[1] if first else "El grafo no tiene fuentes de video"
        return result

    def close(self) -> None:
        """Libera cámaras, archivos y escritores. Es seguro llamarlo varias veces."""
        for _config, source in self._sources.values():
            try:
                source.release()
            except Exception:  # seguir liberando el resto
                pass
        self._sources.clear()
        self.ctx.close_resources()
        self.finished = True
