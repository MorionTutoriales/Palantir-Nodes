"""Genera las capturas de pantalla que usa la documentación (docs/images).

Uso (desde la raíz del proyecto):

    .venv\\Scripts\\python tools\\screenshots.py

Abre la aplicación sin ventana visible (plataforma «offscreen»), arma grafos de ejemplo, los
ejecuta y guarda las imágenes. No toca tus preferencias ni tus nodos personalizados: usa una
carpeta de configuración temporal.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"

# Sin pantalla; las fuentes de Windows para que el texto se vea (la plataforma offscreen no trae).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("QT_SCALE_FACTOR", "2")  # imágenes nítidas al reducirlas en el README
CONFIG = tempfile.mkdtemp(prefix="palantir_shots_")
os.environ["PALANTIR_NODES_CONFIG_DIR"] = CONFIG

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from palantir_nodes.app import install_spanish_qt_translations  # noqa: E402
from palantir_nodes.nodes.registry import load_builtin_nodes  # noqa: E402
from palantir_nodes.ui.compile_dialog import CompileDialog  # noqa: E402
from palantir_nodes.ui.custom_nodes_dialog import CustomNodesDialog  # noqa: E402
from palantir_nodes.ui.libraries_dialog import LibrariesDialog  # noqa: E402
from palantir_nodes.ui.main_window import MainWindow  # noqa: E402
from palantir_nodes.ui.theme import apply_theme  # noqa: E402

MONO = "Consolas" if sys.platform == "win32" else "Monospace"

MARCAR_CAJAS = '''def marcar_cajas(imagen: Image, contornos: Any, area_minima: int = 200,
                 color: Color = (0, 255, 0), grosor: int = 2) -> tuple[Image, int]:
    """Dibuja un rectángulo y un punto central sobre cada contorno y cuenta cuántos hay."""
    salida = imagen.copy()
    cantidad = 0
    for contorno in contornos or []:
        if cv2.contourArea(contorno) < area_minima:
            continue
        x, y, ancho, alto = cv2.boundingRect(contorno)
        bgr = (color[2], color[1], color[0])
        cv2.rectangle(salida, (x, y), (x + ancho, y + alto), bgr, grosor)
        cv2.circle(salida, (x + ancho // 2, y + alto // 2), 4, bgr, -1)
        cantidad += 1
    return salida, cantidad
'''


def wait(ms: int = 150) -> None:
    QTest.qWait(ms)


def make_scene(path: Path) -> None:
    """Escena de ejemplo: fondo con degradado, objetos rojos y de otros colores."""
    height, width = 360, 520
    y, x = np.mgrid[0:height, 0:width]
    image = np.zeros((height, width, 3), np.uint8)
    image[..., 0] = 70 + (x * 40 // width)
    image[..., 1] = 85 + (y * 50 // height)
    image[..., 2] = 80
    rng = np.random.default_rng(4)
    image = np.clip(image.astype(int) + rng.integers(-6, 7, image.shape), 0, 255).astype(np.uint8)
    cv2.circle(image, (110, 110), 52, (40, 40, 215), -1)  # rojo
    cv2.rectangle(image, (230, 60), (330, 170), (30, 35, 200), -1)  # rojo
    cv2.circle(image, (420, 240), 42, (45, 30, 220), -1)  # rojo
    cv2.rectangle(image, (60, 230), (170, 320), (200, 110, 30), -1)  # azul
    cv2.circle(image, (290, 270), 45, (60, 190, 70), -1)  # verde
    cv2.rectangle(image, (400, 60), (480, 120), (40, 190, 230), -1)  # amarillo
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", image)[1].tofile(str(path))


def new_window() -> MainWindow:
    window = MainWindow(load_builtin_nodes().copy())
    window._confirm_discard = lambda: True
    window.resize(1640, 940)
    window.show()
    wait()
    return window


def run_graph(window: MainWindow) -> None:
    window.last_result = None
    window.runner.run(side_effects=False)
    for _ in range(100):
        wait(100)
        if window.last_result is not None:
            break
    wait(300)


def shot(widget, name: str) -> None:
    wait(250)
    widget.grab().save(str(IMAGES / name))
    print("guardada", name)


def editor_red_objects(scene_path: Path) -> None:
    window = new_window()
    ctl, graph = window.controller, window.graph
    load = ctl.add_node("input.load_image", (-1000, -60))
    ctl.set_param(load, "path", str(scene_path))
    low = ctl.add_node("image.in_range", (-720, -240))
    ctl.set_param(low, "lower", (0.0, 120.0, 70.0))
    ctl.set_param(low, "upper", (10.0, 255.0, 255.0))
    high = ctl.add_node("image.in_range", (-720, 70))
    ctl.set_param(high, "lower", (170.0, 120.0, 70.0))
    ctl.set_param(high, "upper", (179.0, 255.0, 255.0))
    union = ctl.add_node("compose.bitwise_or", (-440, -120))
    clean = ctl.add_node("image.morphology", (-170, -120))
    ctl.set_param(clean, "op", "open")
    ctl.set_param(clean, "ksize", 5)
    contours = ctl.add_node("image.find_contours", (110, -120))
    draw = ctl.add_node("image.draw_contours", (380, -120))
    ctl.set_param(draw, "thickness", 4)
    ctl.set_param(draw, "color", (60, 255, 90))
    viewer = ctl.add_node("output.image_viewer", (660, -120))
    for src, sock, dst, dsock in (
        (load, "image", low, "image"),
        (load, "image", high, "image"),
        (low, "mask", union, "image_a"),
        (high, "mask", union, "image_b"),
        (union, "image", clean, "image"),
        (clean, "image", contours, "image"),
        (load, "image", draw, "image"),
        (contours, "contours", draw, "contours"),
        (draw, "image", viewer, "image"),
    ):
        graph.add_link(src, sock, dst, dsock)
    ctl.add_frame(-755, -300, 250, 640, "Detectar rojo")
    window.scene.clearSelection()
    run_graph(window)
    window.view.frame_all()
    window.scene.select_nodes([viewer])
    wait(300)
    window.scene.clearSelection()
    shot(window, "editor-objetos-rojos.png")
    window.close()


def values_and_text() -> None:
    window = new_window()
    ctl, graph = window.controller, window.graph
    slider = ctl.add_node("input.slider", (-760, -140))
    ctl.set_param(slider, "minimum", 0.0)
    ctl.set_param(slider, "maximum", 360.0)
    ctl.set_param(slider, "value", 135.0)
    sine = ctl.add_node("math.sin", (-470, -140))
    ctl.set_param(sine, "unit", "degrees")
    text = ctl.add_node("convert.number_to_string", (-180, -140))
    ctl.set_param(text, "decimals", 3)
    shown = ctl.add_node("output.string_viewer", (110, -140))
    vec = ctl.add_node("input.vector3", (-760, 180))
    ctl.set_param(vec, "value", (1.5, 2.25, -3.0))
    as_json = ctl.add_node("convert.to_json", (-470, 180))
    ctl.set_param(as_json, "compact", True)
    pick = ctl.add_node("convert.json_value", (-180, 180))
    ctl.set_param(pick, "path", "1")
    shown_json = ctl.add_node("output.string_viewer", (110, 180))
    for src, sock, dst, dsock in (
        (slider, "value", sine, "angle"),
        (sine, "result", text, "value"),
        (text, "text", shown, "text"),
        (vec, "vector", as_json, "value"),
        (as_json, "json", pick, "json"),
        (as_json, "json", shown_json, "text"),
    ):
        graph.add_link(src, sock, dst, dsock)
    window.scene.clearSelection()
    run_graph(window)
    window.view.frame_all()
    window.scene.clearSelection()
    window.resize(1500, 760)
    shot(window, "valores-y-texto.png")
    window.close()


def custom_nodes_dialog() -> None:
    window = new_window()
    spec = window.custom_library.create(
        "Marcar cajas", "Mis filtros", MARCAR_CAJAS, "Rectángulo y centro sobre cada objeto"
    )
    dialog = CustomNodesDialog(window.custom_library, window)
    dialog.resize(1180, 780)
    dialog.show()
    dialog.code.setFont(QFont(MONO, 10))
    dialog.info.document().setDefaultStyleSheet(f"code {{ font-family: '{MONO}'; }}")
    dialog.select_entry(spec.id, confirm=False)
    dialog.refresh_analysis()
    shot(dialog, "nodos-personalizados.png")
    dialog._dirty = False
    dialog.close()
    window.close()


def libraries_dialog() -> None:
    window = new_window()
    dialog = LibrariesDialog(["network"], window)
    dialog.resize(900, 560)
    dialog.show()
    dialog.listing.setCurrentRow(0)
    shot(dialog, "librerias.png")
    dialog.close()
    window.close()


def compile_dialog() -> None:
    window = new_window()
    dialog = CompileDialog(
        "print('hola')\n", window, name="detector_rojo", folder="C:/Users/tu/ejecutables"
    )
    dialog.resize(760, 420)
    dialog.show()
    dialog.log.appendPlainText("Aquí aparece el avance de la compilación, línea a línea.")
    shot(dialog, "compilar.png")
    dialog.close()
    window.close()


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Palantir Nodes")
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Sans", 9))
    install_spanish_qt_translations(app)
    apply_theme(app)
    IMAGES.mkdir(parents=True, exist_ok=True)
    scene_path = IMAGES / "escena_ejemplo.png"
    make_scene(scene_path)
    editor_red_objects(scene_path)
    values_and_text()
    custom_nodes_dialog()
    libraries_dialog()
    compile_dialog()


if __name__ == "__main__":
    main()
