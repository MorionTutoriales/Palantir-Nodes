"""Iconos de la interfaz.

Son los de **Lucide** (licencia ISC, compatible con la GPL; ver ``assets/LICENSE-lucide.txt``),
guardados como SVG en ``ui/assets/``. Se dibujan con el color del skin activo, así que cambian
junto con él. ``icon("play")`` devuelve un ``QIcon`` con los estados normal, deshabilitado y
activado (marcado).
"""

from __future__ import annotations

from functools import cache, lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from palantir_nodes.ui.theme import Colors

ICON_DIR = Path(__file__).with_name("assets")
SIZES = (16, 24, 32, 48)  # tamaños que se generan; Qt elige el más cercano

# Icono de cada categoría de nodos (las que no están aquí usan ``DEFAULT_CATEGORY_ICON``).
CATEGORY_ICONS = {
    "Entradas": "log-in",
    "Imagen": "image",
    "Conversión": "arrow-left-right",
    "Matemáticas": "sigma",
    "Composición": "layers",
    "Salidas": "log-out",
    "Red": "network",
    "MediaPipe": "scan-face",
}
DEFAULT_CATEGORY_ICON = "puzzle"


def available_icons() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg") if p.stem != "logo")


@cache
def _svg_text(name: str) -> str:
    path = ICON_DIR / f"{name}.svg"
    if not path.is_file():
        raise FileNotFoundError(f"No existe el icono '{name}' en {ICON_DIR}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1024)
def _render(svg: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def pixmap(name: str, color: str | None = None, size: int = 24) -> QPixmap:
    """El icono dibujado en ``color`` (por defecto, el del texto del skin activo)."""
    svg = _svg_text(name).replace("currentColor", color or Colors.TEXT)
    return _render(svg, size)


def icon(name: str, color: str | None = None, on_color: str | None = None) -> QIcon:
    """Icono con colores para sus estados: normal, deshabilitado y marcado/activado."""
    result = QIcon()
    states = (
        (QIcon.Mode.Normal, QIcon.State.Off, color or Colors.TEXT),
        (QIcon.Mode.Active, QIcon.State.Off, color or Colors.TEXT),
        (QIcon.Mode.Disabled, QIcon.State.Off, Colors.DISABLED),
        (QIcon.Mode.Normal, QIcon.State.On, on_color or Colors.ACCENT_TEXT),
        (QIcon.Mode.Active, QIcon.State.On, on_color or Colors.ACCENT_TEXT),
        (QIcon.Mode.Disabled, QIcon.State.On, Colors.DISABLED),
    )
    for size in SIZES:
        for mode, state, tint in states:
            result.addPixmap(pixmap(name, tint, size), mode, state)
    return result


def category_icon_name(category: str) -> str:
    return CATEGORY_ICONS.get(category, DEFAULT_CATEGORY_ICON)


def app_icon() -> QIcon:
    """El logotipo de la aplicación (colores fijos, no depende del skin)."""
    svg = (ICON_DIR / "logo.svg").read_text(encoding="utf-8")
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(_render(svg, size))
    return result


def clear_cache() -> None:
    """Olvida los iconos ya dibujados (hay que llamarla al cambiar de skin)."""
    _render.cache_clear()
