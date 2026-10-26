"""Punto de entrada de la aplicación."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication

from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui import icons
from palantir_nodes.ui.main_window import APP_NAME, MainWindow
from palantir_nodes.ui.theme import apply_theme


def install_spanish_qt_translations(app: QApplication) -> bool:
    """Traduce los textos estándar de Qt (Guardar, Cancelar, selector de color, etc.).

    Devuelve ``False`` si las traducciones no están disponibles (la aplicación sigue
    funcionando, con esos textos en inglés).
    """
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    installed = False
    for name in ("qtbase_es", "qt_es"):
        translator = QTranslator(app)
        if translator.load(name, folder):
            app.installTranslator(translator)
            installed = True
    return installed


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    install_spanish_qt_translations(app)
    app.setWindowIcon(icons.app_icon())
    apply_theme(app)

    registry = load_builtin_nodes()
    messages = registry.load_entry_points()

    window = MainWindow(registry, startup_messages=messages)
    window.show()
    # python -m palantir_nodes proyecto.json
    paths = [a for a in app.arguments()[1:] if not a.startswith("-")]
    if paths:
        window.load_project(Path(paths[0]))
    else:
        window.reopen_last_project()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
