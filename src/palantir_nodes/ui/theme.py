"""Tema de la interfaz (oscuro, inspirado en Blender) y aplicación de skins."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from palantir_nodes.skins import DEFAULT_SKIN, Skin, get_skin


class Colors:
    WINDOW = "#2B2B2B"
    PANEL = "#303030"
    BASE = "#1F1F1F"
    FIELD = "#3D3D3D"
    FIELD_HOVER = "#474747"
    BORDER = "#1A1A1A"
    TEXT = "#D6D6D6"
    TEXT_DIM = "#8C8C8C"
    ACCENT = "#4772B3"
    ACCENT_TEXT = "#FFFFFF"  # texto e iconos sobre el color de acento

    EDITOR_BG = "#1D1D1D"
    GRID_MINOR = "#242424"
    GRID_MAJOR = "#2C2C2C"
    GRID_AXIS = "#353535"

    MENU_BG = "#262626"  # menús, listas y desplegables
    SEPARATOR = "#3A3A3A"
    DISABLED = "#5E5E5E"  # texto e iconos deshabilitados
    FIELD_DISABLED_TEXT = "#6A6A6A"
    FIELD_DISABLED_BG = "#333333"
    HANDLE = "#CFCFCF"  # el tirador de los deslizadores
    TOOLTIP_BG = "#1A1A1A"

    # El aspecto de los nodos y de las conexiones no depende del skin.
    NODE_BODY = "#303030"
    NODE_BORDER = "#121212"
    NODE_TEXT = "#E6E6E6"
    NODE_FIELD = "#3E3E3E"
    NODE_FIELD_HOVER = "#4D4D4D"
    NODE_SELECTED = "#F5A623"

    LINK_VALID = "#5BD06A"
    LINK_INVALID = "#E0524F"
    LINK_NEUTRAL = "#BDBDBD"
    LINK_SELECTED = "#F5A623"


# Valores originales de cada color: a ellos se vuelve antes de aplicar un skin.
_DEFAULTS = {name: value for name, value in vars(Colors).items() if name.isupper()}

_current_skin = DEFAULT_SKIN


def current_skin() -> Skin:
    return get_skin(_current_skin)


def apply_skin(skin_id: str) -> Skin:
    """Cambia los colores de ``Colors`` a los del skin (el original si no existe)."""
    global _current_skin
    skin = get_skin(skin_id)
    for name, value in _DEFAULTS.items():
        setattr(Colors, name, value)
    for name, value in skin.colors.items():
        setattr(Colors, name, value)
    _current_skin = skin.id
    return skin


def build_stylesheet() -> str:
    """Hoja de estilo con los colores del skin activo."""
    c = Colors
    return f"""
QWidget {{ color: {c.TEXT}; font-size: 9pt; }}
QMainWindow, QDialog {{ background: {c.WINDOW}; }}
QMainWindow::separator {{ background: {c.BORDER}; width: 1px; height: 1px; }}

QDockWidget {{ titlebar-close-icon: none; titlebar-normal-icon: none; }}
QDockWidget::title {{
    background: {c.PANEL}; padding: 5px 8px; border-bottom: 1px solid {c.BORDER};
}}
QWidget#DockTitle {{
    background: {c.PANEL}; border-bottom: 1px solid {c.BORDER};
}}
QWidget#DockTitle QLabel {{ font-weight: 600; }}
QWidget#DockTitle QToolButton {{ padding: 0; border-radius: 4px; }}

QToolBar {{
    background: {c.PANEL}; border: none; border-bottom: 1px solid {c.BORDER};
    spacing: 3px; padding: 4px 6px;
}}
QToolBar::separator {{ width: 1px; background: {c.SEPARATOR}; margin: 5px 6px; }}
QToolBar#view_toolbar {{
    border-bottom: 1px solid {c.BORDER}; padding: 3px 6px;
}}
QToolButton {{ padding: 4px 9px; border-radius: 5px; border: 1px solid transparent; }}
QToolButton:hover {{ background: {c.FIELD_HOVER}; }}
QToolButton:pressed {{ background: {c.ACCENT}; color: {c.ACCENT_TEXT}; }}
QToolButton:checked {{ background: {c.ACCENT}; color: {c.ACCENT_TEXT}; }}
QToolButton:disabled {{ color: {c.DISABLED}; background: transparent; }}
QToolButton[primary="true"] {{
    background: {c.ACCENT}; color: {c.ACCENT_TEXT}; font-weight: 600; padding: 4px 12px;
}}
QToolButton[primary="true"]:hover {{ border: 1px solid {c.ACCENT_TEXT}; }}
QToolButton[primary="true"]:disabled {{ background: {c.FIELD}; color: {c.DISABLED}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QMenuBar {{ background: {c.PANEL}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 4px 8px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {c.FIELD_HOVER}; }}
QMenu {{ background: {c.MENU_BG}; border: 1px solid {c.BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 10px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c.ACCENT}; color: {c.ACCENT_TEXT}; }}
QMenu::item:disabled {{ color: {c.DISABLED}; }}
QMenu::separator {{ height: 1px; background: {c.SEPARATOR}; margin: 4px 6px; }}
QMenu::icon {{ padding-left: 6px; }}

QStatusBar {{ background: {c.PANEL}; border-top: 1px solid {c.BORDER}; }}
QStatusBar QLabel {{ padding: 0 4px; }}
QStatusBar::item {{ border: none; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {c.FIELD}; border: 1px solid {c.BORDER}; border-radius: 5px;
    padding: 2px 6px; min-height: 18px; selection-background-color: {c.ACCENT};
    selection-color: {c.ACCENT_TEXT};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    background: {c.FIELD_HOVER};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c.ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {c.FIELD_DISABLED_TEXT}; background: {c.FIELD_DISABLED_BG};
}}
QComboBox QAbstractItemView {{
    background: {c.MENU_BG}; selection-background-color: {c.ACCENT};
    selection-color: {c.ACCENT_TEXT}; border: 1px solid {c.BORDER};
}}
QPushButton {{
    background: {c.FIELD}; border: 1px solid {c.BORDER}; border-radius: 5px;
    padding: 4px 12px;
}}
QPushButton:hover {{ background: {c.FIELD_HOVER}; }}
QPushButton:disabled {{ color: {c.DISABLED}; }}
QPushButton[primary="true"] {{
    background: {c.ACCENT}; color: {c.ACCENT_TEXT}; border: 1px solid {c.ACCENT}; font-weight: 600;
}}
QCheckBox::indicator {{ width: 14px; height: 14px; }}

QSlider::groove:horizontal {{ height: 4px; background: {c.BASE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c.ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {c.HANDLE}; border: 1px solid {c.BORDER}; width: 10px; margin: -5px 0;
    border-radius: 6px;
}}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {c.FIELD_HOVER}; min-height: 24px; border-radius: 4px; margin: 1px;
}}
QScrollBar::handle:vertical:hover {{ background: {c.DISABLED}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {c.FIELD_HOVER}; min-width: 24px; border-radius: 4px; margin: 1px;
}}
QScrollBar::handle:horizontal:hover {{ background: {c.DISABLED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QListWidget, QTreeWidget {{ background: {c.MENU_BG}; border: none; outline: none; }}
QListWidget::item {{ padding: 4px 6px; }}
QListWidget::item:selected {{ background: {c.ACCENT}; color: {c.ACCENT_TEXT}; }}
QTreeWidget::item {{ padding: 4px 4px; border-radius: 4px; }}
QTreeWidget::item:hover {{ background: {c.FIELD_HOVER}; }}
QTreeWidget::item:selected {{ background: {c.ACCENT}; color: {c.ACCENT_TEXT}; }}
QTextBrowser, QPlainTextEdit {{ selection-background-color: {c.ACCENT}; }}
QGroupBox {{
    border: 1px solid {c.SEPARATOR}; border-radius: 6px; margin-top: 12px; padding-top: 8px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {c.TEXT_DIM}; }}
QToolTip {{
    background: {c.TOOLTIP_BG}; color: {c.TEXT}; border: 1px solid {c.SEPARATOR};
}}
"""


def apply_theme(app: QApplication, skin_id: str = DEFAULT_SKIN) -> Skin:
    """Aplica el skin (colores, paleta y hoja de estilo) a toda la aplicación."""
    skin = apply_skin(skin_id)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(Colors.WINDOW))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(Colors.BASE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(Colors.PANEL))
    palette.setColor(QPalette.ColorRole.Text, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(Colors.FIELD))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(Colors.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Colors.ACCENT_TEXT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(Colors.TOOLTIP_BG))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(Colors.TEXT_DIM))
    disabled = QPalette.ColorGroup.Disabled
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        palette.setColor(disabled, role, QColor(Colors.FIELD_DISABLED_TEXT))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet())
    return skin
