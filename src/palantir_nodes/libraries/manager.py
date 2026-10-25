"""Activación de librerías en un registro de nodos."""

from __future__ import annotations

from palantir_nodes.libraries import LibraryInfo, available_libraries, get_library
from palantir_nodes.nodes.registry import NodeRegistry


class LibraryManager:
    """Registra y quita los nodos de las librerías activas del proyecto."""

    def __init__(self, registry: NodeRegistry) -> None:
        self.registry = registry
        self._enabled: list[str] = []

    @property
    def enabled(self) -> list[str]:
        return list(self._enabled)

    def is_enabled(self, library_id: str) -> bool:
        return library_id in self._enabled

    def enable(self, library_id: str) -> LibraryInfo:
        library = get_library(library_id)
        if library is None:
            raise KeyError(f"No existe la librería '{library_id}'")
        if library_id not in self._enabled:
            for cls in library.nodes:
                self.registry.replace(cls)
            self._enabled.append(library_id)
        return library

    def disable(self, library_id: str) -> None:
        library = get_library(library_id)
        if library is None or library_id not in self._enabled:
            return
        for cls in library.nodes:
            self.registry.unregister(cls.type_id)
        self._enabled.remove(library_id)

    def type_ids(self, library_id: str) -> list[str]:
        library = get_library(library_id)
        return [cls.type_id for cls in library.nodes] if library else []

    def library_of(self, type_id: str) -> LibraryInfo | None:
        return next(
            (lib for lib in available_libraries() if any(c.type_id == type_id for c in lib.nodes)),
            None,
        )

    def set_enabled(self, library_ids: list[str]) -> list[str]:
        """Deja activas exactamente ``library_ids``. Devuelve los identificadores desconocidos."""
        unknown = [i for i in library_ids if get_library(i) is None]
        wanted = [i for i in library_ids if i not in unknown]
        for library_id in self.enabled:
            if library_id not in wanted:
                self.disable(library_id)
        for library_id in wanted:
            self.enable(library_id)
        return unknown
