"""Especificaciones declarativas de entradas, salidas y parámetros de un nodo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from palantir_nodes.core.errors import ParamValidationError
from palantir_nodes.core.types import SocketType


class ParamKind(Enum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    STRING = "string"
    FILE_PATH = "file_path"
    COLOR = "color"
    VECTOR2 = "vector2"
    VECTOR3 = "vector3"


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


@dataclass(frozen=True)
class ParamSpec:
    """Parámetro configurable de un nodo.

    Los colores se almacenan como tuplas RGB de enteros 0-255; cada nodo es responsable
    de convertirlos a BGR al procesar con OpenCV.
    """

    name: str
    kind: ParamKind
    default: Any
    label: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    decimals: int = 3
    options: tuple[tuple[str, str], ...] = ()  # (valor, etiqueta) para ENUM
    slider: bool = False
    file_filter: str = ""
    save_dialog: bool = False
    tooltip: str = ""

    @property
    def display_label(self) -> str:
        return self.label or _humanize(self.name)

    def _clamp(self, value: float) -> float:
        if self.minimum is not None and value < self.minimum:
            value = type(value)(self.minimum)
        if self.maximum is not None and value > self.maximum:
            value = type(value)(self.maximum)
        return value

    def coerce(self, value: Any) -> Any:
        """Valida y normaliza ``value``. Lanza :class:`ParamValidationError` si no es válido."""
        try:
            return self._coerce(value)
        except ParamValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ParamValidationError(
                f"Valor inválido para '{self.display_label}': {value!r} ({exc})"
            ) from exc

    def _coerce(self, value: Any) -> Any:
        match self.kind:
            case ParamKind.INT:
                if isinstance(value, float) and not value.is_integer():
                    value = round(value)
                return self._clamp(int(value))
            case ParamKind.FLOAT:
                return self._clamp(float(value))
            case ParamKind.BOOL:
                if isinstance(value, bool):
                    return value
                if value in (0, 1):
                    return bool(value)
                raise ParamValidationError(f"'{self.display_label}' debe ser verdadero o falso")
            case ParamKind.ENUM:
                valid = [opt for opt, _ in self.options]
                if value not in valid:
                    raise ParamValidationError(
                        f"'{value}' no es una opción de '{self.display_label}' ({', '.join(valid)})"
                    )
                return value
            case ParamKind.STRING | ParamKind.FILE_PATH:
                if not isinstance(value, str):
                    raise ParamValidationError(f"'{self.display_label}' debe ser texto")
                return value
            case ParamKind.COLOR:
                rgb = tuple(int(c) for c in value)
                if len(rgb) != 3:
                    raise ParamValidationError(f"'{self.display_label}' necesita 3 componentes")
                return tuple(max(0, min(255, c)) for c in rgb)
            case ParamKind.VECTOR2 | ParamKind.VECTOR3:
                size = 2 if self.kind is ParamKind.VECTOR2 else 3
                vec = tuple(float(c) for c in value)
                if len(vec) != size:
                    raise ParamValidationError(
                        f"'{self.display_label}' necesita {size} componentes"
                    )
                return tuple(self._clamp(c) for c in vec)
        raise ParamValidationError(f"Tipo de parámetro desconocido: {self.kind}")

    def format(self, value: Any) -> str:
        """Representación corta del valor para mostrar dentro del nodo."""
        match self.kind:
            case ParamKind.FLOAT:
                return f"{value:.{self.decimals}f}"
            case ParamKind.BOOL:
                return "Sí" if value else "No"
            case ParamKind.ENUM:
                return dict(self.options).get(value, str(value))
            case ParamKind.FILE_PATH:
                return os.path.basename(value) if value else "—"
            case ParamKind.COLOR:
                return "#{:02X}{:02X}{:02X}".format(*value)
            case ParamKind.VECTOR2 | ParamKind.VECTOR3:
                return "(" + ", ".join(f"{c:.2f}" for c in value) + ")"
            case _:
                return str(value) if value != "" else "—"


_EDITABLE_INPUT_KINDS: dict[SocketType, ParamKind] = {
    SocketType.FLOAT: ParamKind.FLOAT,
    SocketType.INTEGER: ParamKind.INT,
    SocketType.BOOLEAN: ParamKind.BOOL,
    SocketType.STRING: ParamKind.STRING,
    SocketType.COLOR: ParamKind.COLOR,
    SocketType.VECTOR2: ParamKind.VECTOR2,
    SocketType.VECTOR3: ParamKind.VECTOR3,
}


@dataclass(frozen=True)
class InputSpec:
    """Entrada de un nodo. Si ``default`` no es ``None``, el valor es editable sin conexión."""

    name: str
    type: SocketType
    label: str = ""
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    tooltip: str = ""

    def __post_init__(self) -> None:
        if self.default is not None and self.type not in _EDITABLE_INPUT_KINDS:
            raise ValueError(
                f"La entrada '{self.name}' de tipo {self.type.value} no admite valor por defecto"
            )

    @property
    def display_label(self) -> str:
        return self.label or _humanize(self.name)

    @property
    def has_default(self) -> bool:
        return self.default is not None

    def value_spec(self) -> ParamSpec | None:
        """Especificación del valor editable cuando la entrada no está conectada."""
        if self.default is None:
            return None
        return ParamSpec(
            name=self.name,
            kind=_EDITABLE_INPUT_KINDS[self.type],
            default=self.default,
            label=self.label,
            minimum=self.minimum,
            maximum=self.maximum,
            step=self.step,
            tooltip=self.tooltip,
        )


@dataclass(frozen=True)
class OutputSpec:
    name: str
    type: SocketType
    label: str = ""
    tooltip: str = ""

    @property
    def display_label(self) -> str:
        return self.label or _humanize(self.name)
