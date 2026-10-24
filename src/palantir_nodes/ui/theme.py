"""Tema oscuro inspirado en Blender."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


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

    EDITOR_BG = "#1D1D1D"
    GRID_MINOR = "#242424"
    GRID_MAJOR = "#2C2C2C"
    GRID_AXIS = "#353535"

    NODE_BODY = "#303030"
    NODE_BORDER = "#121212"
    NODE_TEXT = "#E6E6E6"
    NODE_FIELD = "#3E3E3E"
    NODE_SELECTED = "#F5A623"

    LINK_VALID = "#5BD06A"
    LINK_INVALID = "#E0524F"
    LINK_NEUTRAL = "#BDBDBD"
    LINK_SELECTED = "#F5A623"


STYLESHEET = f"""
QWidget {{ color: {Colors.TEXT}; font-size: 9pt; }}
QMainWindow, QDialog {{ background: {Colors.WINDOW}; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{
    background: {Colors.PANEL}; padding: 5px 8px; border-bottom: 1px solid {Colors.BORDER};
}}
QToolBar {{
    background: {Colors.PANEL}; border: none; border-bottom: 1px solid {Colors.BORDER};
    spacing: 2px; padding: 3px;
}}
QToolButton {{ padding: 4px 10px; border-radius: 4px; }}
QToolButton:hover {{ background: {Colors.FIELD_HOVER}; }}
QToolButton:pressed {{ background: {Colors.ACCENT}; }}
QToolButton:disabled {{ color: #5E5E5E; }}
QMenuBar {{ background: {Colors.PANEL}; }}
QMenuBar::item:selected {{ background: {Colors.FIELD_HOVER}; }}
QMenu {{ background: #262626; border: 1px solid {Colors.BORDER}; padding: 4px; }}
QMenu::item {{ padding: 4px 22px 4px 14px; border-radius: 3px; }}
QMenu::item:selected {{ background: {Colors.ACCENT}; }}
QMenu::item:disabled {{ color: #5E5E5E; }}
QMenu::separator {{ height: 1px; background: #3A3A3A; margin: 4px 6px; }}
QStatusBar {{ background: {Colors.PANEL}; border-top: 1px solid {Colors.BORDER}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {Colors.FIELD}; border: 1px solid {Colors.BORDER}; border-radius: 4px;
    padding: 2px 6px; min-height: 18px; selection-background-color: {Colors.ACCENT};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    background: {Colors.FIELD_HOVER};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: #6A6A6A; background: #333333;
}}
QComboBox QAbstractItemView {{ background: #262626; selection-background-color: {Colors.ACCENT}; }}
QPushButton {{
    background: {Colors.FIELD}; border: 1px solid {Colors.BORDER}; border-radius: 4px;
    padding: 3px 10px;
}}
QPushButton:hover {{ background: {Colors.FIELD_HOVER}; }}
QSlider::groove:horizontal {{ height: 4px; background: {Colors.BASE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {Colors.ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #CFCFCF; width: 10px; margin: -4px 0; border-radius: 5px;
}}
QScrollArea {{ border: none; }}
QListWidget {{ background: #262626; border: none; outline: none; }}
QListWidget::item {{ padding: 4px 6px; }}
QListWidget::item:selected {{ background: {Colors.ACCENT}; }}
QGroupBox {{
    border: 1px solid #3A3A3A; border-radius: 4px; margin-top: 12px; padding-top: 6px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {Colors.TEXT_DIM}; }}
QToolTip {{ background: #1A1A1A; color: {Colors.TEXT}; border: 1px solid #3A3A3A; }}
"""


def apply_theme(app: QApplication) -> None:
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
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(Colors.TEXT_DIM))
    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QPalette.ColorRole.Text, QColor("#6A6A6A"))
    palette.setColor(disabled, QPalette.ColorRole.ButtonText, QColor("#6A6A6A"))
    palette.setColor(disabled, QPalette.ColorRole.WindowText, QColor("#6A6A6A"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
