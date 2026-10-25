"""Biblioteca de nodos incluida.

En la Fase 1 los nodos declaran sus sockets y parámetros; su procesamiento y generación
de código se implementan en las Fases 3 y 4 (hasta entonces lanzan
``NodeNotImplementedError``).
"""

from palantir_nodes.nodes.library import color, compose, convert, image, inputs, math, outputs  # noqa: F401
