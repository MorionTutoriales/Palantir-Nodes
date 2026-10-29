"""Autocomprobación: ``python -m palantir_nodes --selftest``.

Arranca la interfaz sin mostrarla, ejecuta un grafo pequeño, genera su script y cambia de skin.
Sirve para comprobar que una versión empaquetada (el ejecutable de una *release*) trae todo lo que
necesita —iconos, módulos que se cargan al vuelo, el código fuente que usa el exportador—, y
termina con código 0 si todo está bien. No toca tus preferencias ni tus nodos personalizados.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path


def run() -> int:
    """Devuelve 0 si todo funciona; si no, imprime el motivo y devuelve 1."""
    config = os.environ.get("PALANTIR_NODES_CONFIG_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="palantir_selftest_") as folder:
            os.environ["PALANTIR_NODES_CONFIG_DIR"] = str(Path(folder) / "config")
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            _check(Path(folder))
    except Exception:
        _report("Autocomprobación fallida:\n" + traceback.format_exc(), error=True)
        return 1
    finally:  # no dejar la carpeta de configuración temporal como la de la sesión
        if config is None:
            os.environ.pop("PALANTIR_NODES_CONFIG_DIR", None)
        else:
            os.environ["PALANTIR_NODES_CONFIG_DIR"] = config
    _report("Autocomprobación correcta")
    return 0


def _report(message: str, *, error: bool = False) -> None:
    """Escribe el resultado en la consola y, si existe la variable, en un archivo.

    El ejecutable de una release no tiene consola (es una aplicación de ventanas), así que quien
    lo comprueba indica ``PALANTIR_SELFTEST_LOG`` para leer el resultado.
    """
    print(message, file=sys.stderr if error else sys.stdout)
    log = os.environ.get("PALANTIR_SELFTEST_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def _check(folder: Path) -> None:
    import cv2
    import numpy as np
    from PySide6.QtWidgets import QApplication  # Qt antes que OpenCV (como en la aplicación)

    from palantir_nodes import __version__
    from palantir_nodes.codegen import CodeGenerator
    from palantir_nodes.core.graph import Graph
    from palantir_nodes.engine.executor import ExecContext, Executor
    from palantir_nodes.engine.plan import ExecutionPlan
    from palantir_nodes.libraries import available_libraries
    from palantir_nodes.nodes.registry import load_builtin_nodes
    from palantir_nodes.skins import SKINS
    from palantir_nodes.ui import icons
    from palantir_nodes.ui.main_window import MainWindow
    from palantir_nodes.ui.theme import apply_theme

    registry = load_builtin_nodes().copy()
    assert len(registry) >= 50, f"faltan nodos: {len(registry)}"

    # El motor y el exportador (que lee el código fuente de sus propias funciones).
    source = folder / "entrada.png"
    cv2.imencode(".png", np.full((24, 32, 3), 90, np.uint8))[1].tofile(str(source))
    graph = Graph(registry)
    load = graph.add_node("input.load_image", params={"path": str(source)})
    gray = graph.add_node("image.grayscale")
    save = graph.add_node("output.save_image", params={"path": str(folder / "salida.png")})
    graph.add_link(load.id, "image", gray.id, "image")
    graph.add_link(gray.id, "image", save.id, "image")
    plan = ExecutionPlan.from_graph(graph)
    result = Executor().run(plan, ExecContext(side_effects=True))
    assert result.ok and (folder / "salida.png").exists(), result.errors
    code = CodeGenerator(plan, __version__).generate()
    assert "def main" in code and "cv2.cvtColor" in code, "el script exportado está incompleto"

    # Las librerías opcionales (sus nodos se cargan al activarlas).
    for library in available_libraries():
        for node in library.nodes:
            assert node.type_id and node.label

    # La interfaz: iconos, skins y ventana principal (Qt necesita su aplicación antes de dibujar).
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    assert len(icons.available_icons()) >= 40, "faltan los iconos"
    assert not icons.app_icon().isNull()
    window = MainWindow(registry)
    window.show()
    for skin_id in SKINS:
        window.apply_skin(skin_id)
    app.processEvents()
    assert window.palette.visible_node_ids(), "el panel de nodos está vacío"
    window.close()
    window.deleteLater()
    app.processEvents()
