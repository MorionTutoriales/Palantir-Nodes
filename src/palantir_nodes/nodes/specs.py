"""Especificaciones declarativas de entradas, salidas y parámetros de un nodo."""

from __future__ import annotations

import math
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


# Tipos de parámetro que pueden recibir su valor desde otro nodo y el tipo de socket que usan.
_PARAM_SOCKET_TYPES: dict[ParamKind, SocketType] = {
    ParamKind.INT: SocketType.INTEGER,
    ParamKind.FLOAT: SocketType.FLOAT,
    ParamKind.BOOL: SocketType.BOOLEAN,
    ParamKind.COLOR: SocketType.COLOR,
    ParamKind.VECTOR2: SocketType.VECTOR2,
    ParamKind.VECTOR3: SocketType.VECTOR3,
}


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
    # Si el tipo lo permite, el parámetro tiene además un socket de entrada: se puede escribir
    # el valor o conectar la salida de otro nodo (que entonces lo sustituye).
    connectable: bool = True
    # Parámetro numérico que el nodo dibuja como deslizador cuyo rango sale de otros parámetros:
    # (nombre del mínimo, nombre del máximo, nombre de la casilla «solo enteros»).
    range_params: tuple[str, str, str] | None = None

    @property
    def display_label(self) -> str:
        return self.label or _humanize(self.name)

    @property
    def socket_type(self) -> SocketType | None:
        """Tipo del socket de entrada del parámetro, o ``None`` si no se puede conectar."""
        return _PARAM_SOCKET_TYPES.get(self.kind) if self.connectable else None

    def as_input(self) -> InputSpec | None:
        """El socket del parámetro como una entrada con valor por defecto editable."""
        socket_type = self.socket_type
        if socket_type is None:
            return None
        return InputSpec(
            self.name,
            socket_type,
            label=self.label,
            default=self.default,
            minimum=self.minimum,
            maximum=self.maximum,
            step=self.step,
            tooltip=self.tooltip,
        )

    def coerce_expr(self, expr: str) -> str:
        """Expresión Python equivalente a :meth:`coerce` para un valor que llega por un socket.

        Solo para los tipos con socket. El script exportado la usa para que un valor conectado
        se recorte y normalice igual que en el motor.
        """

        def clamp(inner: str, cast: str) -> str:
            if self.minimum is not None:
                inner = f"max({inner}, {self._bound(self.minimum, cast)})"
            if self.maximum is not None:
                inner = f"min({inner}, {self._bound(self.maximum, cast)})"
            return inner

        match self.kind:
            case ParamKind.INT:
                return clamp(f"int(round({expr}))", "int")
            case ParamKind.FLOAT:
                return clamp(f"float({expr})", "float")
            case ParamKind.BOOL:
                return f"bool({expr})"
            case ParamKind.COLOR:
                return f"tuple(max(0, min(255, int(c))) for c in {expr})"
            case ParamKind.VECTOR2 | ParamKind.VECTOR3:
                return f"tuple({clamp('float(c)', 'float')} for c in {expr})"
        raise ValueError(f"El parámetro '{self.name}' ({self.kind.value}) no tiene socket")

    @staticmethod
    def _bound(value: float, cast: str) -> str:
        return repr(int(value) if cast == "int" else float(value))

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


def resolve_slider(
    minimum: float, maximum: float, value: float, integer: bool
) -> tuple[float, float, float]:
    """Rango efectivo y valor de un deslizador: ``(mínimo, máximo, valor)``.

    Si los extremos están al revés se intercambian; en modo entero el rango se reduce a los
    enteros que contiene y el valor se redondea. El valor siempre queda dentro del rango.
    """
    low, high = sorted((float(minimum), float(maximum)))
    if integer:
        low, high = math.ceil(low), max(math.ceil(low), math.floor(high))
        value = round(value)
    value = min(max(float(value), low), high)
    return float(low), float(high), float(value)


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
    # Entrada que puede quedar sin conectar: el nodo recibe ``None`` en su lugar.
    optional: bool = False

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
