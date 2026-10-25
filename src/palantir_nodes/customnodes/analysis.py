"""Análisis estático del código de un nodo personalizado (nunca lo ejecuta).

Detecta la función del nodo (la última función pública del módulo), sus entradas a partir
de los parámetros y sus salidas a partir del tipo de retorno.
"""

from __future__ import annotations

import ast
import keyword
from dataclasses import dataclass, field
from typing import Any

from palantir_nodes.core.errors import PalantirError
from palantir_nodes.core.types import SocketType
from palantir_nodes.customnodes.runtime import factory_source
from palantir_nodes.nodes.specs import InputSpec

T = SocketType

_NAMES: dict[str, SocketType] = {
    "int": T.INTEGER,
    "float": T.FLOAT,
    "bool": T.BOOLEAN,
    "str": T.STRING,
    "Color": T.COLOR,
    "Vector2": T.VECTOR2,
    "Vector3": T.VECTOR3,
    "Image": T.IMAGE,
    "ndarray": T.IMAGE,
    "Any": T.ANY,
    "object": T.ANY,
}
_IMAGE_ATTRIBUTES = {
    "np.ndarray",
    "numpy.ndarray",
    "cv2.Mat",
    "cv2.typing.MatLike",
    "np.typing.NDArray",
    "numpy.typing.NDArray",
}
_TUPLE_NAMES = {"tuple", "Tuple", "typing.Tuple"}
_LITERAL_NAMES = {"Literal", "typing.Literal"}
_NDARRAY_GENERIC = {"NDArray", "np.typing.NDArray", "numpy.typing.NDArray"}
_NEUTRAL_DEFAULTS: dict[SocketType, Any] = {
    T.INTEGER: 0,
    T.FLOAT: 0.0,
    T.BOOLEAN: False,
    T.STRING: "",
    T.COLOR: (0, 0, 0),
    T.VECTOR2: (0.0, 0.0),
    T.VECTOR3: (0.0, 0.0, 0.0),
}
SUPPORTED_TYPES = (
    "Image, int, float, bool, str, Color, Vector2, Vector3, Any, tuple[...], Literal['a', 'b']"
)


@dataclass(frozen=True)
class Issue:
    message: str
    line: int | None = None

    def __str__(self) -> str:
        return f"línea {self.line}: {self.message}" if self.line else self.message


@dataclass(frozen=True)
class ParamInfo:
    """Parámetro de la función. ``kind``: ``"input"`` (socket) o ``"enum"`` (lista)."""

    name: str
    kind: str
    socket_type: SocketType | None
    default: Any = None
    optional: bool = False
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputInfo:
    name: str
    socket_type: SocketType


@dataclass
class Analysis:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    function_name: str = ""
    params: list[ParamInfo] = field(default_factory=list)
    outputs: list[OutputInfo] = field(default_factory=list)
    description: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors and bool(self.function_name)


class _Unsupported(PalantirError):
    pass


@dataclass(frozen=True)
class _Type:
    socket: SocketType
    options: tuple[str, ...] = ()  # solo para Literal (lista desplegable)


def _dotted(node: ast.expr) -> str | None:
    """``np.ndarray`` → ``"np.ndarray"``; ``None`` si no es un nombre con puntos."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _resolve(node: ast.expr, *, allow_literal: bool = True) -> _Type:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):  # anotación como texto
        try:
            return _resolve(ast.parse(node.value, mode="eval").body, allow_literal=allow_literal)
        except SyntaxError:
            raise _Unsupported(f"anotación no válida: {node.value!r}") from None
    if isinstance(node, ast.Constant) and node.value is None:
        raise _Unsupported("None no es un tipo de dato (usa un valor por defecto = None)")
    name = _dotted(node)
    if name is not None:
        if name in _NAMES:
            return _Type(_NAMES[name])
        if name in _IMAGE_ATTRIBUTES:
            return _Type(T.IMAGE)
        raise _Unsupported(f"tipo no soportado '{name}'. Usa: {SUPPORTED_TYPES}")
    if isinstance(node, ast.Subscript):
        base = _dotted(node.value)
        index = node.slice
        if base in _NDARRAY_GENERIC:
            return _Type(T.IMAGE)
        if base in _TUPLE_NAMES:
            return _resolve_tuple(index)
        if base in _LITERAL_NAMES:
            items = index.elts if isinstance(index, ast.Tuple) else [index]
            values = [
                i.value for i in items if isinstance(i, ast.Constant) and isinstance(i.value, str)
            ]
            if not values or len(values) != len(items):
                raise _Unsupported("Literal solo admite textos, p. ej. Literal['a', 'b']")
            if len(set(values)) != len(values):
                raise _Unsupported("Literal tiene opciones repetidas")
            if not allow_literal:
                return _Type(T.STRING)
            return _Type(T.STRING, tuple(values))
        raise _Unsupported(f"tipo no soportado '{base or '?'}[...]'. Usa: {SUPPORTED_TYPES}")
    raise _Unsupported(f"anotación no soportada. Usa: {SUPPORTED_TYPES}")


def _resolve_tuple(index: ast.expr) -> _Type:
    items = index.elts if isinstance(index, ast.Tuple) else [index]
    kinds = [_dotted(i) for i in items]
    if kinds and all(k in ("int", "float") for k in kinds):
        if len(kinds) == 2:
            return _Type(T.VECTOR2)
        if len(kinds) == 3:
            return _Type(T.COLOR if all(k == "int" for k in kinds) else T.VECTOR3)
    raise _Unsupported(
        "tuple solo se admite como tuple[float, float] (Vector2), tuple[float, float, float] "
        "(Vector3) o tuple[int, int, int] (Color)"
    )


def _infer_from_default(value: Any) -> SocketType | None:
    if isinstance(value, bool):
        return T.BOOLEAN
    if isinstance(value, int):
        return T.INTEGER
    if isinstance(value, float):
        return T.FLOAT
    if isinstance(value, str):
        return T.STRING
    if isinstance(value, tuple) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
    ):
        if len(value) == 2:
            return T.VECTOR2
        if len(value) == 3:
            all_bytes = all(isinstance(v, int) and 0 <= v <= 255 for v in value)
            return T.COLOR if all_bytes else T.VECTOR3
    return None


def _own_returns(function: ast.FunctionDef) -> list[ast.Return]:
    """``return`` de la función, sin los de funciones, clases o lambdas anidadas."""
    found: list[ast.Return] = []
    stack: list[ast.AST] = list(function.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return):
            found.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return sorted(found, key=lambda r: r.lineno)


def _is_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _output_names(function: ast.FunctionDef, count: int) -> list[str] | None:
    """Nombres de salida tomados de ``return a, b`` si todos los ``return`` coinciden."""
    candidates: list[list[str]] = []
    for ret in _own_returns(function):
        value = ret.value
        if value is None or _is_none(value):
            continue
        if count == 1:
            names = [value.id] if isinstance(value, ast.Name) else None
        else:
            ok = isinstance(value, ast.Tuple) and len(value.elts) == count
            names = [e.id for e in value.elts if isinstance(e, ast.Name)] if ok else None
            if names is not None and len(names) != count:
                names = None
        if names is None:
            return None
        candidates.append(names)
    if not candidates or any(c != candidates[0] for c in candidates):
        return None
    names = candidates[0]
    valid = len(set(names)) == len(names) and all(
        n.isidentifier() and not keyword.iskeyword(n) for n in names
    )
    return names if valid else None


def _neutral_or_checked_default(
    name: str, kind: SocketType, node: ast.expr | None, analysis: Analysis, line: int
) -> Any:
    """Valor por defecto de un parámetro escalar: el declarado (validado) o uno neutro."""
    if node is None:
        return _NEUTRAL_DEFAULTS[kind]
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        analysis.errors.append(
            Issue(
                f"el valor por defecto de '{name}' debe ser un literal (número, texto, True/False, tupla)",
                line,
            )
        )
        return _NEUTRAL_DEFAULTS[kind]
    if value is None:
        analysis.warnings.append(
            Issue(
                f"'{name}' = None no es válido para {kind.value}; se usa {_NEUTRAL_DEFAULTS[kind]!r}",
                line,
            )
        )
        return _NEUTRAL_DEFAULTS[kind]
    spec = InputSpec(name, kind, default=_NEUTRAL_DEFAULTS[kind]).value_spec()
    try:
        return spec.coerce(value)
    except PalantirError as exc:
        analysis.errors.append(
            Issue(f"el valor por defecto de '{name}' no es {kind.value}: {exc}", line)
        )
        return _NEUTRAL_DEFAULTS[kind]


def analyze(code: str) -> Analysis:
    """Analiza el código del nodo. No lo ejecuta."""
    analysis = Analysis()
    if not code.strip():
        analysis.errors.append(Issue("Escribe el código del nodo: una función con sus parámetros."))
        return analysis
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        analysis.errors.append(Issue(f"sintaxis: {exc.msg}", exc.lineno))
        return analysis

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            analysis.errors.append(Issue("no se admite 'from __future__ import ...'", node.lineno))

    functions = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    ]
    if not functions:
        analysis.errors.append(
            Issue(
                "No hay ninguna función pública. Define una con `def nombre(...):` (las que empiezan por _ se ignoran)."
            )
        )
        return analysis
    function = functions[-1]
    if isinstance(function, ast.AsyncFunctionDef):
        analysis.errors.append(Issue("la función del nodo no puede ser async", function.lineno))
        return analysis
    analysis.function_name = function.name
    analysis.description = (ast.get_docstring(function) or "").strip().split("\n")[0]
    if len(functions) > 1:
        analysis.warnings.append(
            Issue(
                f"Hay varias funciones públicas: el nodo usa la última, '{function.name}'.",
                function.lineno,
            )
        )

    _analyze_params(function, analysis)
    _analyze_outputs(function, analysis)

    if not analysis.errors:  # errores que solo aparecen al compilar dentro de la función fábrica
        try:
            compile(factory_source(code, function.name), "<analisis>", "exec")
        except SyntaxError as exc:
            line = exc.lineno - 1 if exc.lineno and exc.lineno > 1 else exc.lineno
            analysis.errors.append(Issue(f"sintaxis: {exc.msg}", line))
    return analysis


def _analyze_params(function: ast.FunctionDef, analysis: Analysis) -> None:
    args = function.args
    if args.posonlyargs:
        analysis.errors.append(
            Issue("no se admiten parámetros solo posicionales (con /)", function.lineno)
        )
    if args.vararg or args.kwarg:
        analysis.errors.append(Issue("no se admiten *args ni **kwargs", function.lineno))

    positional = list(args.args)
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults)) + list(
        args.defaults
    )
    entries = list(zip(positional, defaults, strict=True)) + list(
        zip(args.kwonlyargs, args.kw_defaults, strict=True)
    )
    for arg, default_node in entries:
        line = arg.lineno
        kind: _Type | None = None
        if arg.annotation is not None:
            try:
                kind = _resolve(arg.annotation)
            except _Unsupported as exc:
                analysis.errors.append(Issue(f"parámetro '{arg.arg}': {exc}", line))
                continue
        default_value: Any = None
        has_literal = False
        if default_node is not None:
            try:
                default_value, has_literal = ast.literal_eval(default_node), True
            except (ValueError, SyntaxError):
                has_literal = False
        if kind is None:
            inferred = _infer_from_default(default_value) if has_literal else None
            if inferred is None:
                analysis.warnings.append(
                    Issue(
                        f"'{arg.arg}' no tiene tipo: se usa Any. Anótalo, p. ej. `{arg.arg}: Image`.",
                        line,
                    )
                )
                kind = _Type(T.ANY)
            else:
                kind = _Type(inferred)

        socket = kind.socket
        if kind.options:  # Literal -> lista desplegable
            choice = kind.options[0]
            if has_literal:
                if default_value not in kind.options:
                    analysis.errors.append(
                        Issue(
                            f"el valor por defecto de '{arg.arg}' no está entre {list(kind.options)}",
                            line,
                        )
                    )
                else:
                    choice = default_value
            analysis.params.append(
                ParamInfo(arg.arg, "enum", T.STRING, choice, options=kind.options)
            )
        elif socket in (T.IMAGE, T.ANY):
            optional = False
            if default_node is not None:
                if has_literal and default_value is None:
                    optional = True
                else:
                    analysis.errors.append(
                        Issue(
                            f"'{arg.arg}' ({socket.value}) solo admite None como valor por defecto",
                            line,
                        )
                    )
            analysis.params.append(ParamInfo(arg.arg, "input", socket, optional=optional))
        else:
            if default_node is not None and not has_literal:
                analysis.errors.append(
                    Issue(
                        f"el valor por defecto de '{arg.arg}' debe ser un literal (número, texto, True/False, tupla)",
                        line,
                    )
                )
                continue
            value = _neutral_or_checked_default(arg.arg, socket, default_node, analysis, line)
            analysis.params.append(ParamInfo(arg.arg, "input", socket, default=value))


def _analyze_outputs(function: ast.FunctionDef, analysis: Analysis) -> None:
    returns = function.returns
    returns_value = any(
        r.value is not None and not _is_none(r.value) for r in _own_returns(function)
    )

    if returns is None:
        if returns_value:
            analysis.warnings.append(
                Issue(
                    "sin anotación de retorno: la salida es de tipo Any. Añade `-> Image` (o el tipo) para poder conectarla.",
                    function.lineno,
                )
            )
            analysis.outputs.append(OutputInfo("result", T.ANY))
        return
    if _is_none(returns):
        if returns_value:
            analysis.warnings.append(
                Issue("la función declara `-> None` pero devuelve un valor", function.lineno)
            )
        return

    try:
        # En el retorno, tuple[...] siempre son varias salidas; un vector se declara con
        # Vector2 / Vector3 / Color.
        multiple = (
            isinstance(returns, ast.Subscript)
            and _dotted(returns.value) in _TUPLE_NAMES
            and isinstance(returns.slice, ast.Tuple)
        )
        if multiple:
            kinds = [_resolve(e, allow_literal=False).socket for e in returns.slice.elts]
        else:
            kinds = [_resolve(returns, allow_literal=False).socket]
    except _Unsupported as exc:
        analysis.errors.append(Issue(f"tipo de retorno: {exc}", function.lineno))
        return

    names = _output_names(function, len(kinds))
    if names is None:
        names = ["result"] if len(kinds) == 1 else [f"result_{i + 1}" for i in range(len(kinds))]
    analysis.outputs.extend(OutputInfo(n, k) for n, k in zip(names, kinds, strict=True))
