"""Panel «Nodos»: categorías y nodos con buscador; se añaden con doble clic o arrastrando."""

from __future__ import annotations

import weakref

import shiboken6
from PySide6.QtCore import QMimeData, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.nodes.categories import get_category
from palantir_nodes.nodes.registry import NodeRegistry
from palantir_nodes.ui import icons

NODE_MIME = "application/x-palantir-node"  # el contenido es el type_id del nodo
TYPE_ROLE = Qt.ItemDataRole.UserRole


def _swatch(color: str) -> QIcon:
    pixmap = QPixmap(10, 10)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class _NodeTree(QTreeWidget):
    """Árbol cuyos nodos se pueden arrastrar hasta el editor."""

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return [NODE_MIME]

    def mimeData(self, items) -> QMimeData:  # noqa: N802
        data = QMimeData()
        type_ids = [i.data(0, TYPE_ROLE) for i in items if i.data(0, TYPE_ROLE)]
        data.setData(NODE_MIME, "\n".join(type_ids).encode("utf-8"))
        return data

    def startDrag(self, supported_actions) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None or not item.data(0, TYPE_ROLE):
            return  # las categorías no se arrastran
        drag = QDrag(self)
        drag.setMimeData(self.mimeData([item]))
        drag.exec(Qt.DropAction.CopyAction)


class NodePalette(QWidget):
    """Lista de nodos por categoría. Emite ``node_requested(type_id)`` al elegir uno."""

    node_requested = Signal(str)

    def __init__(self, registry: NodeRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.registry = registry
        self._expanded: set[str] = {"Imagen"}

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar nodos…")
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(
            icons.icon("search"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.tree = _NodeTree()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setIconSize(self.tree.iconSize() * 1.15)
        self.tree.setRootIsDecorated(True)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setToolTipDuration(8000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)

        self.search.textChanged.connect(self.apply_filter)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemActivated.connect(self._on_double_click)  # Enter
        self.tree.itemExpanded.connect(lambda item: self._remember(item, True))
        self.tree.itemCollapsed.connect(lambda item: self._remember(item, False))
        self.search.returnPressed.connect(self._add_first_match)
        self._refresh_pending = False
        self._watch_registry()
        self.refresh()

    def _watch_registry(self) -> None:
        """Se actualiza sola cuando se añaden o quitan nodos (librerías, nodos personalizados)."""
        ref = weakref.ref(self)

        def changed() -> None:
            palette = ref()
            if palette is not None and shiboken6.isValid(palette):
                palette._schedule_refresh()

        registry = self.registry
        registry.subscribe(changed)
        self.destroyed.connect(lambda *_: registry.unsubscribe(changed))

    def _schedule_refresh(self) -> None:
        if not self._refresh_pending:  # varios cambios seguidos = una sola actualización
            self._refresh_pending = True
            QTimer.singleShot(0, self._refresh_now)

    def _refresh_now(self) -> None:
        self._refresh_pending = False
        if shiboken6.isValid(self):
            self.refresh()

    # -- contenido ----------------------------------------------------------------------

    def refresh(self) -> None:
        """Vuelve a leer el registro (nodos personalizados y librerías) y los colores del skin."""
        self.tree.blockSignals(True)
        self.tree.clear()
        self._search_action.setIcon(icons.icon("search"))
        for category, members in self.registry.by_category().items():
            top = QTreeWidgetItem([f"{category}  ({len(members)})"])
            top.setData(0, Qt.ItemDataRole.UserRole + 1, category)
            color = get_category(category).color
            top.setIcon(0, icons.icon(icons.category_icon_name(category), color=color))
            top.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(top)
            for cls in members:
                child = QTreeWidgetItem([cls.label])
                child.setData(0, TYPE_ROLE, cls.type_id)
                child.setIcon(0, _swatch(color))
                child.setToolTip(0, cls.description or cls.label)
                top.addChild(child)
        self.tree.blockSignals(False)
        self.apply_filter(self.search.text())

    def _remember(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if self.search.text().strip():
            return  # al filtrar todo se expande; no es una decisión del usuario
        category = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if category:
            (self._expanded.add if expanded else self._expanded.discard)(category)

    def apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        for index in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(index)
            category = top.data(0, Qt.ItemDataRole.UserRole + 1)
            visible = 0
            for child_index in range(top.childCount()):
                child = top.child(child_index)
                type_id = child.data(0, TYPE_ROLE)
                cls = self.registry.get(type_id)
                haystack = f"{child.text(0)} {category} {type_id} {cls.description if cls else ''}"
                match = not query or query in haystack.lower()
                child.setHidden(not match)
                visible += match
            top.setHidden(visible == 0)
            top.setExpanded(bool(query) or category in self._expanded)

    def visible_node_ids(self) -> list[str]:
        """Los nodos que se ven ahora mismo, en orden."""
        found = []
        for index in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(index)
            if top.isHidden():
                continue
            for child_index in range(top.childCount()):
                child = top.child(child_index)
                if not child.isHidden():
                    found.append(child.data(0, TYPE_ROLE))
        return found

    # -- elegir un nodo ---------------------------------------------------------------------

    def _on_double_click(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        type_id = item.data(0, TYPE_ROLE)
        if type_id:
            self.node_requested.emit(type_id)
        else:
            item.setExpanded(not item.isExpanded())

    def _add_first_match(self) -> None:
        matches = self.visible_node_ids()
        if matches:
            self.node_requested.emit(matches[0])
