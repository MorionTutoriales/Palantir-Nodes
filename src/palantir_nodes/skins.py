"""Skins (aspecto) de la interfaz. Este módulo no depende de Qt.

Un skin cambia el aspecto de la aplicación —ventana, paneles, barras, menús, campos y el fondo
del lienzo— pero **nunca el de los nodos ni sus conexiones**: los colores que empiezan por
``NODE_`` y ``LINK_`` no se pueden sobrescribir. Un skin solo lista lo que cambia respecto al
aspecto original (``oscuro``, que no cambia nada).
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SKIN = "oscuro"

# Colores que un skin puede cambiar. El aspecto de los nodos y de las conexiones queda fuera.
THEMEABLE = (
    "WINDOW",
    "PANEL",
    "BASE",
    "FIELD",
    "FIELD_HOVER",
    "BORDER",
    "TEXT",
    "TEXT_DIM",
    "ACCENT",
    "ACCENT_TEXT",
    "EDITOR_BG",
    "GRID_MINOR",
    "GRID_MAJOR",
    "GRID_AXIS",
    "MENU_BG",
    "SEPARATOR",
    "DISABLED",
    "FIELD_DISABLED_TEXT",
    "FIELD_DISABLED_BG",
    "HANDLE",
    "TOOLTIP_BG",
)


@dataclass(frozen=True)
class Skin:
    id: str
    label: str
    description: str
    colors: dict[str, str] = field(default_factory=dict)  # solo lo que cambia

    def __post_init__(self) -> None:
        unknown = set(self.colors) - set(THEMEABLE)
        if unknown:
            raise ValueError(f"El skin '{self.id}' cambia colores no permitidos: {sorted(unknown)}")


SKINS: dict[str, Skin] = {
    skin.id: skin
    for skin in (
        Skin("oscuro", "Oscuro", "Gris oscuro neutro, inspirado en Blender (el original)."),
        Skin(
            "medianoche",
            "Medianoche",
            "Azul profundo, con acento azul vivo.",
            {
                "WINDOW": "#1A1F2E",
                "PANEL": "#202638",
                "BASE": "#141824",
                "FIELD": "#2B3350",
                "FIELD_HOVER": "#364064",
                "BORDER": "#101420",
                "TEXT": "#D5DAEA",
                "TEXT_DIM": "#8590AD",
                "ACCENT": "#5B8DEF",
                "EDITOR_BG": "#111522",
                "GRID_MINOR": "#171C2B",
                "GRID_MAJOR": "#1E2436",
                "GRID_AXIS": "#283049",
                "MENU_BG": "#1C2133",
                "SEPARATOR": "#2E3652",
                "DISABLED": "#566080",
                "FIELD_DISABLED_TEXT": "#667090",
                "FIELD_DISABLED_BG": "#232A40",
                "HANDLE": "#C9D2EE",
                "TOOLTIP_BG": "#10141F",
            },
        ),
        Skin(
            "bosque",
            "Bosque",
            "Verdes apagados y acento esmeralda.",
            {
                "WINDOW": "#232A27",
                "PANEL": "#2A332F",
                "BASE": "#1B211E",
                "FIELD": "#36423D",
                "FIELD_HOVER": "#415049",
                "BORDER": "#161B19",
                "TEXT": "#D8E2DC",
                "TEXT_DIM": "#8A9C92",
                "ACCENT": "#3FA37A",
                "EDITOR_BG": "#1A201D",
                "GRID_MINOR": "#202723",
                "GRID_MAJOR": "#27302B",
                "GRID_AXIS": "#313C36",
                "MENU_BG": "#222925",
                "SEPARATOR": "#3A4741",
                "DISABLED": "#5C6B63",
                "FIELD_DISABLED_TEXT": "#6B7A72",
                "FIELD_DISABLED_BG": "#2E3833",
                "HANDLE": "#D0DDD6",
                "TOOLTIP_BG": "#161B19",
            },
        ),
        Skin(
            "claro",
            "Claro",
            "Grises claros para trabajar con mucha luz; los nodos conservan su aspecto.",
            {
                "WINDOW": "#E4E6EA",
                "PANEL": "#F3F4F6",
                "BASE": "#FFFFFF",
                "FIELD": "#FFFFFF",
                "FIELD_HOVER": "#EEF0F3",
                "BORDER": "#C3C7CE",
                "TEXT": "#1F2430",
                "TEXT_DIM": "#667085",
                "ACCENT": "#3F72D8",
                "EDITOR_BG": "#D3D6DB",
                "GRID_MINOR": "#CBCED4",
                "GRID_MAJOR": "#C2C6CD",
                "GRID_AXIS": "#B4B9C1",
                "MENU_BG": "#FFFFFF",
                "SEPARATOR": "#D5D8DE",
                "DISABLED": "#A3A9B5",
                "FIELD_DISABLED_TEXT": "#9AA1AE",
                "FIELD_DISABLED_BG": "#ECEEF1",
                "HANDLE": "#FFFFFF",
                "TOOLTIP_BG": "#FFFFFF",
            },
        ),
    )
}


def get_skin(skin_id: str) -> Skin:
    """El skin pedido o, si no existe, el original."""
    return SKINS.get(skin_id) or SKINS[DEFAULT_SKIN]
