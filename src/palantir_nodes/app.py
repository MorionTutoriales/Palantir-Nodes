"""Punto de entrada de la aplicación."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui.main_window import APP_NAME, MainWindow
from palantir_nodes.ui.theme import apply_theme


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    apply_theme(app)

    registry = load_builtin_nodes()
    messages = registry.load_entry_points()

    window = MainWindow(registry, startup_messages=messages)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
