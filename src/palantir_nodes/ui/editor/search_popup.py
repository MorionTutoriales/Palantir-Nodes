"""Buscador de nodos por nombre o categoría."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from palantir_nodes.nodes.categories import get_category
from palantir_nodes.nodes.registry import NodeRegistry


class NodeSearchPopup(QFrame):
    node_chosen = Signal(str)

    def __init__(self, registry: NodeRegistry, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("NodeSearchPopup")
        self.setStyleSheet(
            "#NodeSearchPopup { background: #262626; border: 1px solid #111; border-radius: 4px; }"
        )
        self._registry = registry
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Buscar nodo por nombre o categoría…")
        self.list = QListWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self.edit)
        layout.addWidget(self.list)
        self.resize(300, 340)

        self.edit.textChanged.connect(self._filter)
        self.edit.installEventFilter(self)
        self.list.itemActivated.connect(self._choose_item)
        self.list.itemClicked.connect(self._choose_item)
        self._filter("")

    def _filter(self, text: str) -> None:
        self.list.clear()
        for cls in self._registry.search(text):
            item = QListWidgetItem(f"{cls.label}    —  {cls.category}")
            item.setData(Qt.ItemDataRole.UserRole, cls.type_id)
            item.setToolTip(cls.description)
            item.setData(Qt.ItemDataRole.DecorationRole, QColor(get_category(cls.category).color))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                if 0 <= row < self.list.count():
                    self.list.setCurrentRow(row)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._choose_item(self.list.currentItem())
                return True
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def _choose_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        type_id = item.data(Qt.ItemDataRole.UserRole)
        self.close()
        self.node_chosen.emit(type_id)

    def popup_at(self, global_pos: QPoint) -> None:
        self.move(global_pos)
        self.show()
        self.edit.setFocus()
