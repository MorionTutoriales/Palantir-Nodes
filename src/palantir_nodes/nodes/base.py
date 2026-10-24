"""Contrato común que implementa cada tipo de nodo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from palantir_nodes.core.errors import NodeNotImplementedError
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamSpec


@dataclass
class CodeFragment:
    """Código Python generado por un nodo.

    ``lines`` son las sentencias y ``outputs`` asocia cada salida del nodo con la
    expresión (normalmente un nombre de variable) que contiene su valor.
    """

    lines: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)


class NodeDefinition:
    """Base de todos los tipos de nodo.

    Un tipo de nodo se declara como subclase con atributos de clase y se registra con
    ``@register_node``. El editor, el motor de ejecución y el exportador solo usan esta
    interfaz, de modo que añadir un nodo no requiere modificarlos.

    - ``process`` recibe los valores de entrada (ya convertidos) y los parámetros, y
      devuelve un diccionario ``{nombre_salida: valor}``.
    - ``generate_code`` recibe las expresiones Python de cada entrada y devuelve un
      :class:`CodeFragment` equivalente a ``process``.
    """

    type_id: ClassVar[str] = ""
    label: ClassVar[str] = ""
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""
    inputs: ClassVar[tuple[InputSpec, ...]] = ()
    outputs: ClassVar[tuple[OutputSpec, ...]] = ()
    params: ClassVar[tuple[ParamSpec, ...]] = ()
    imports: ClassVar[frozenset[str]] = frozenset()
    # Los nodos fuente producen fotogramas (video, cámara) y marcan el modo tiempo real.
    is_source: ClassVar[bool] = False
    # Los nodos con efectos externos (escribir archivos) no se reutilizan desde la caché.
    cacheable: ClassVar[bool] = True

    @classmethod
    def cache_key_extra(cls, params: dict[str, Any]) -> Any:
        """Datos externos que invalidan la caché (p. ej. la fecha de un archivo)."""
        return ()

    @classmethod
    def input(cls, name: str) -> InputSpec | None:
        return next((spec for spec in cls.inputs if spec.name == name), None)

    @classmethod
    def output(cls, name: str) -> OutputSpec | None:
        return next((spec for spec in cls.outputs if spec.name == name), None)

    @classmethod
    def param(cls, name: str) -> ParamSpec | None:
        return next((spec for spec in cls.params if spec.name == name), None)

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {spec.name: spec.coerce(spec.default) for spec in cls.params}

    @classmethod
    def default_input_values(cls) -> dict[str, Any]:
        values = {}
        for spec in cls.inputs:
            value_spec = spec.value_spec()
            if value_spec is not None:
                values[spec.name] = value_spec.coerce(value_spec.default)
        return values

    @classmethod
    def is_implemented(cls) -> bool:
        """``True`` si el nodo ya tiene procesamiento real."""
        return cls.process is not NodeDefinition.process

    def process(self, ctx: Any, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        raise NodeNotImplementedError(
            f"El nodo '{self.label}' todavía no tiene procesamiento implementado"
        )

    def generate_code(
        self, gen: Any, inputs: dict[str, str], params: dict[str, Any]
    ) -> CodeFragment:
        raise NodeNotImplementedError(
            f"El nodo '{self.label}' todavía no tiene generación de código implementada"
        )
