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
    # Instalar solo este paquete, sin sus dependencias. Evita que pip reemplace paquetes
    # que la aplicación ya tiene cargados (p. ej. ``cv2.pyd``, que Windows no deja pisar).
    no_deps: bool = False

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

    def install_steps(
        self, missing: list[Requirement] | None = None
    ) -> list[tuple[bool, list[str]]]:
        """Comandos de pip para instalar lo que falta: ``(sin_dependencias, paquetes)`` por paso."""
        missing = self.missing if missing is None else missing
        bare = [r.package for r in missing if r.no_deps]
        normal = [r.package for r in missing if not r.no_deps]
        return [(True, bare)] * bool(bare) + [(False, normal)] * bool(normal)

    @property
    def install_command(self) -> str:
        """Los comandos de ``pip install`` de todos los paquetes de la librería, uno por línea."""
        steps = self.install_steps(list(self.requirements))
        return "\n".join(
            "pip install " + ("--no-deps " if bare else "") + " ".join(packages)
            for bare, packages in steps
        )


def available_libraries() -> list[LibraryInfo]:
    """Todas las librerías incluidas, en el orden en que se muestran."""
    from palantir_nodes.libraries.mediapipe_lib import LIBRARY as mediapipe
    from palantir_nodes.libraries.network import LIBRARY as network
    from palantir_nodes.libraries.tcp import LIBRARY as tcp

    return [network, tcp, mediapipe]


def get_library(library_id: str) -> LibraryInfo | None:
    return next((lib for lib in available_libraries() if lib.id == library_id), None)
