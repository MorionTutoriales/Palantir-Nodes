"""Jerarquía de errores del proyecto."""


class PalantirError(Exception):
    """Base de todos los errores propios de Palantir Nodes."""


class GraphError(PalantirError):
    """Operación inválida sobre el grafo."""


class UnknownNodeTypeError(GraphError):
    """Se pidió un tipo de nodo que no está registrado."""


class ConnectionRejectedError(GraphError):
    """Una conexión no cumple las reglas de validación."""


class CycleError(GraphError):
    """El grafo contiene (o contendría) un ciclo de dependencias."""


class ParamValidationError(PalantirError):
    """Un valor no es válido para el parámetro o entrada indicada."""


class RegistryError(PalantirError):
    """Definición de nodo inválida o registro duplicado."""


class NodeNotImplementedError(PalantirError):
    """El nodo existe pero su procesamiento o generación de código aún no está implementado."""
