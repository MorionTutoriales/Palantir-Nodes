"""Ejecución del grafo con caché por contenido y aislamiento de errores por nodo.

Cada nodo tiene una clave que resume su tipo, parámetros, valores por defecto y las
claves de sus entradas conectadas. Si la clave coincide con la de la ejecución anterior se
reutiliza el resultado; así solo se recalculan los nodos afectados por un cambio, sin
necesidad de notificaciones de invalidación (y sin carreras entre hilos).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from palantir_nodes.core.types import SocketType, conversion_between
from palantir_nodes.engine.plan import ExecutionPlan, PlanNode
from palantir_nodes.engine.thumbnails import make_thumbnail


@dataclass
class ExecContext:
    """Contexto que reciben los nodos al procesar.

    ``side_effects`` es ``False`` en las ejecuciones automáticas: los nodos que escriben
    en disco deben omitir la escritura.
    """

    side_effects: bool = True
    # Modo tiempo real: las fuentes entregan un fotograma por iteración en ``frames``.
    realtime: bool = False
    frame_index: int = 0
    frames: dict[str, Any] = field(default_factory=dict)
    # Nodo que se está procesando (lo fija el ejecutor antes de cada ``process``).
    node_id: str = ""
    # Recursos con ciclo de vida (p. ej. VideoWriter): nodo -> (clave, objeto, cierre).
    resources: dict[str, tuple[Any, Any, Callable[[], None]]] = field(default_factory=dict)
    # Si se indica (ancho, alto), el resultado incluye miniaturas de las imágenes de cada nodo.
    preview_max: tuple[int, int] | None = None

    def close_resources(self) -> None:
        """Libera todos los recursos abiertos por los nodos; nunca lanza."""
        for _key, _obj, closer in list(self.resources.values()):
            try:
                closer()
            except Exception:  # un cierre fallido no debe impedir cerrar el resto
                pass
        self.resources.clear()


@dataclass
class ExecutionResult:
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    images: dict[str, np.ndarray] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    blocked: dict[str, str] = field(default_factory=dict)
    computed: set[str] = field(default_factory=set)
    cached: set[str] = field(default_factory=set)
    times_ms: dict[str, float] = field(default_factory=dict)
    total_ms: float = 0.0
    fps: float | None = None  # solo en tiempo real
    # nodo -> miniatura. ``None`` = no se calcularon (desactivadas o limitadas por frecuencia),
    # distinto de ``{}`` = se calcularon y ningún nodo tiene imagen.
    previews: dict[str, np.ndarray] | None = None

    @property
    def ok(self) -> bool:
        return not self.errors and not self.blocked


def _freeze(outputs: dict[str, Any]) -> None:
    """Marca los arrays como solo lectura: los resultados cacheados se comparten."""
    for value in outputs.values():
        if isinstance(value, np.ndarray):
            value.flags.writeable = False


def _first_image(values: dict[str, Any], specs) -> np.ndarray | None:
    for spec in specs:
        value = values.get(spec.name)
        if spec.type is SocketType.IMAGE and isinstance(value, np.ndarray):
            return value
    return None


class Executor:
    """Mantiene la caché entre ejecuciones. Úsalo desde un único hilo a la vez."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, dict[str, Any]]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def run(self, plan: ExecutionPlan, ctx: ExecContext | None = None) -> ExecutionResult:
        ctx = ctx or ExecContext()
        result = ExecutionResult()
        keys: dict[str, str] = {}
        started = time.perf_counter()

        for node_id in plan.order:
            node = plan.nodes[node_id]
            definition = node.definition
            incoming = plan.incoming.get(node_id, {})

            failed = [
                src for src, _ in incoming.values() if src in result.errors or src in result.blocked
            ]
            if failed:
                label = plan.nodes[failed[0]].definition.label
                result.blocked[node_id] = f"Depende de '{label}', que no se pudo calcular"
                continue

            try:
                inputs, key = self._resolve(plan, node, incoming, result, keys, ctx)
            except Exception as exc:
                result.errors[node_id] = str(exc)
                continue
            keys[node_id] = key
            result.inputs[node_id] = inputs

            entry = self._cache.get(node_id)
            if definition.cacheable and entry is not None and entry[0] == key:
                outputs = entry[1]
                result.cached.add(node_id)
                result.times_ms[node_id] = 0.0
            else:
                t0 = time.perf_counter()
                try:
                    ctx.node_id = node_id
                    outputs = definition().process(ctx, inputs, dict(node.params))
                    missing = [s.name for s in definition.outputs if s.name not in outputs]
                    if missing:
                        raise RuntimeError(f"El nodo no produjo la salida '{missing[0]}'")
                except Exception as exc:
                    self._cache.pop(node_id, None)
                    result.errors[node_id] = _describe(exc)
                    continue
                result.times_ms[node_id] = (time.perf_counter() - t0) * 1000
                result.computed.add(node_id)
                _freeze(outputs)
                if definition.cacheable:
                    self._cache[node_id] = (key, outputs)

            result.outputs[node_id] = outputs
            image = _first_image(outputs, definition.outputs)
            if image is None:
                image = _first_image(inputs, definition.inputs)
            if image is not None:
                result.images[node_id] = image

        for stale in set(self._cache) - set(plan.nodes):
            del self._cache[stale]
        result.total_ms = (time.perf_counter() - started) * 1000
        if ctx.preview_max is not None:
            width, height = ctx.preview_max
            result.previews = {
                node_id: make_thumbnail(image, width, height)
                for node_id, image in result.images.items()
            }
        return result

    @staticmethod
    def _resolve(
        plan: ExecutionPlan,
        node: PlanNode,
        incoming: dict[str, tuple[str, str]],
        result: ExecutionResult,
        keys: dict[str, str],
        ctx: ExecContext,
    ) -> tuple[dict[str, Any], str]:
        inputs: dict[str, Any] = {}
        parts: list[Any] = []
        for spec in node.definition.inputs:
            if spec.name in incoming:
                src_id, src_socket = incoming[spec.name]
                value = result.outputs[src_id][src_socket]
                src_spec = plan.nodes[src_id].definition.output(src_socket)
                conversion = conversion_between(src_spec.type, spec.type)
                if conversion is not None:
                    value = conversion.convert(value)
                parts.append((spec.name, "link", keys[src_id], src_socket, spec.type.value))
            elif spec.has_default:
                value = node.input_values[spec.name]
                parts.append((spec.name, "value", repr(value)))
            else:
                raise ValueError(f"Falta conectar la entrada '{spec.display_label}'")
            inputs[spec.name] = value

        raw = repr(
            (
                node.definition.type_id,
                sorted(node.params.items()),
                node.definition.cache_key_extra(node.params),
                # Una fuente produce un fotograma distinto en cada iteración.
                ctx.frame_index if node.definition.is_source else None,
                parts,
            )
        )
        return inputs, hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _describe(exc: Exception) -> str:
    text = str(exc).strip()
    if isinstance(exc, (ValueError, RuntimeError, OSError)) and text:
        return text
    name = type(exc).__name__
    # Los mensajes de cv2.error son muy largos; se conserva la última línea útil.
    if text:
        text = [line for line in text.splitlines() if line.strip()][-1]
    return f"{name}: {text}" if text else name
