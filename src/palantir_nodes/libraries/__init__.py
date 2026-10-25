"""Librerías adicionales de nodos que cada proyecto puede activar.

Una librería agrupa nodos que dependen de paquetes externos (o que no todos necesitan). No
se registran al arrancar: el proyecto las activa y el gestor (:mod:`.manager`) añade sus
nodos al registro. El script exportado importa lo que esos nodos necesitan.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from palantir_nodes.nodes.base import NodeDefinition


@dataclass(frozen=True)
class Requirement:
    """Paquete de Python del que depende una librería."""

    module: str  # nombre con el que se importa
    package: str  # nombre para ``pip install``

    @property
    def installed(self) -> bool:
        try:
            return importlib.util.find_spec(self.module) is not None
        except (ImportError, ValueError):
            return False


@dataclass(frozen=True)
class LibraryInfo:
    id: str
    label: str
    description: str
    nodes: tuple[type[NodeDefinition], ...]
    requirements: tuple[Requirement, ...] = ()

    @property
    def missing(self) -> list[Requirement]:
        """Dependencias que no están instaladas en este equipo."""
        return [r for r in self.requirements if not r.installed]

    @property
    def install_command(self) -> str:
        return "pip install " + " ".join(r.package for r in self.requirements)


def available_libraries() -> list[LibraryInfo]:
    """Todas las librerías incluidas, en el orden en que se muestran."""
    from palantir_nodes.libraries.mediapipe_lib import LIBRARY as mediapipe
    from palantir_nodes.libraries.network import LIBRARY as network
    from palantir_nodes.libraries.tcp import LIBRARY as tcp

    return [network, tcp, mediapipe]


def get_library(library_id: str) -> LibraryInfo | None:
    return next((lib for lib in available_libraries() if lib.id == library_id), None)
