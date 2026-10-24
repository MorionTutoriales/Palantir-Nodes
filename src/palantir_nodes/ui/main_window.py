"""Ventana principal: editor central, paneles acoplables y barra superior."""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QMessageBox, QToolBar

from palantir_nodes import __version__
from palantir_nodes.core.graph import Graph, GraphEvent
from palantir_nodes.nodes.registry import NodeRegistry
from palantir_nodes.ui.editor.controller import EditorController
from palantir_nodes.ui.editor.scene import NodeScene
from palantir_nodes.ui.editor.view import NodeView
from palantir_nodes.ui.properties.panel import PropertiesPanel
from palantir_nodes.ui.run_controller import RunController
from palantir_nodes.ui.viewer.panel import ViewerPanel

APP_NAME = "Palantir Nodes"

# Acciones de la barra superior que todavía no tienen implementación real.
_PENDING = {
    "open": ("Abrir proyecto…", "Ctrl+O", "Guardado/carga JSON: pendiente"),
    "save": ("Guardar", "Ctrl+S", "Guardado/carga JSON: pendiente"),
    "save_as": ("Guardar como…", "Ctrl+Shift+S", "Guardado/carga JSON: pendiente"),
    "stop": ("Detener", "Shift+F5", "Ejecución en tiempo real: Fase 5"),
    "export": ("Exportar Python…", "Ctrl+E", "Exportación a Python: Fase 4"),
    "prefs": ("Preferencias…", "", "Preferencias: pendiente"),
}


class MainWindow(QMainWindow):
    def __init__(self, registry: NodeRegistry, startup_messages: list[str] | None = None) -> None:
        super().__init__()
        self.registry = registry
        self.graph = Graph(registry)
        self.undo_stack = QUndoStack(self)
        self.controller = EditorController(self.graph, self.undo_stack)
        self.scene = NodeScene(self.graph, self.controller, self)
        self.view = NodeView(self.scene, self.controller, registry)
        self.setCentralWidget(self.view)

        self.properties = PropertiesPanel(self.graph, self.controller)
        self.viewer = ViewerPanel()
        self.runner = RunController(self.graph, self)
        self.last_result = None
        self.properties_dock = self._dock("Propiedades", self.properties, "properties")
        self.viewer_dock = self._dock("Visor", self.viewer, "viewer")
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.viewer_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        self.splitDockWidget(self.viewer_dock, self.properties_dock, Qt.Orientation.Vertical)
        self.resizeDocks([self.viewer_dock], [340], Qt.Orientation.Horizontal)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_statusbar()

        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.runner.started.connect(lambda: self.show_message("Procesando…", 0))
        self.runner.finished.connect(self._on_run_finished)
        self.scene.status_message.connect(self.show_message)
        self.controller.status_message.connect(self.show_message)
        self.view.zoom_changed.connect(self._update_zoom_label)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self.graph.subscribe(self._on_graph_event)

        self.resize(1400, 860)
        self._update_title()
        self._update_counts()
        self.view.setFocus()
        for message in startup_messages or []:
            self.show_message(message, 8000)

    def _dock(self, title: str, widget, name: str) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        return dock

    # -- acciones ----------------------------------------------------------------------

    def _create_actions(self) -> None:
        self.action_new = QAction("Nuevo", self)
        self.action_new.setShortcut(QKeySequence("Ctrl+N"))
        self.action_new.triggered.connect(self.new_project)

        self.action_run = QAction("Ejecutar", self)
        self.action_run.setShortcut(QKeySequence("F5"))
        self.action_run.setToolTip("Ejecutar el grafo (F5). Save Image solo escribe aquí.")
        self.action_run.triggered.connect(lambda: self.runner.run(side_effects=True))
        self.action_auto = QAction("Auto", self)
        self.action_auto.setCheckable(True)
        self.action_auto.setChecked(True)
        self.action_auto.setToolTip("Ejecutar automáticamente al modificar el grafo")
        self.action_auto.toggled.connect(self._set_auto_run)

        self.pending_actions: dict[str, QAction] = {}
        for key, (text, shortcut, reason) in _PENDING.items():
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.setEnabled(False)
            action.setToolTip(f"{text.rstrip('…')} — no implementado ({reason})")
            action.setStatusTip(f"No implementado todavía: {reason}")
            self.pending_actions[key] = action

        self.action_undo = self.undo_stack.createUndoAction(self, "Deshacer")
        self.action_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.action_redo = self.undo_stack.createRedoAction(self, "Rehacer")
        self.action_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])

        self.action_quit = QAction("Salir", self)
        self.action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_quit.triggered.connect(self.close)

    def _create_menus(self) -> None:
        bar = self.menuBar()
        p = self.pending_actions
        file_menu = bar.addMenu("&Archivo")
        file_menu.addAction(self.action_new)
        file_menu.addAction(p["open"])
        file_menu.addSeparator()
        file_menu.addAction(p["save"])
        file_menu.addAction(p["save_as"])
        file_menu.addSeparator()
        file_menu.addAction(p["export"])
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

        edit_menu = bar.addMenu("&Editar")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        for action in self.view.editor_actions():
            if action is None:
                edit_menu.addSeparator()
            else:
                edit_menu.addAction(action)
        edit_menu.addSeparator()
        edit_menu.addAction(p["prefs"])

        view_menu = bar.addMenu("&Ver")
        view_menu.addAction(self.view.action_frame)
        view_menu.addSeparator()
        view_menu.addAction(self.properties_dock.toggleViewAction())
        view_menu.addAction(self.viewer_dock.toggleViewAction())

        run_menu = bar.addMenu("E&jecución")
        run_menu.addAction(self.action_run)
        run_menu.addAction(self.action_auto)
        run_menu.addAction(p["stop"])

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        p = self.pending_actions
        toolbar.addAction(self.action_new)
        toolbar.addAction(p["open"])
        toolbar.addAction(p["save"])
        toolbar.addAction(p["save_as"])
        toolbar.addSeparator()
        toolbar.addAction(self.action_run)
        toolbar.addAction(self.action_auto)
        toolbar.addAction(p["stop"])
        toolbar.addSeparator()
        toolbar.addAction(p["export"])
        toolbar.addSeparator()
        toolbar.addAction(p["prefs"])
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    def _create_statusbar(self) -> None:
        status = self.statusBar()
        self._counts_label = QLabel()
        self._zoom_label = QLabel()
        status.addPermanentWidget(self._counts_label)
        status.addPermanentWidget(self._zoom_label)
        self._update_zoom_label(self.view.zoom)

    # -- comportamiento ----------------------------------------------------------------

    def show_message(self, text: str, timeout: int = 4000) -> None:
        self.statusBar().showMessage(text, timeout)

    def _update_title(self, *_) -> None:
        dirty = "" if self.undo_stack.isClean() else " *"
        self.setWindowTitle(f"Sin título{dirty} — {APP_NAME} {__version__}")

    def _update_zoom_label(self, zoom: float) -> None:
        self._zoom_label.setText(f"Zoom {zoom * 100:.0f}%")

    def _update_counts(self) -> None:
        self._counts_label.setText(
            f"{len(self.graph.nodes)} nodos · {len(self.graph.links)} conexiones   "
        )

    def _on_graph_event(self, event: GraphEvent) -> None:
        self._update_counts()

    def _on_selection_changed(self) -> None:
        # La escena emite selectionChanged también mientras se destruye.
        if shiboken6.isValid(self.scene) and shiboken6.isValid(self.properties):
            self.properties.show_selection(self.scene.selected_node_ids())
            self._update_viewer()

    def _set_auto_run(self, enabled: bool) -> None:
        self.runner.auto_run = enabled
        self.show_message("Ejecución automática " + ("activada" if enabled else "desactivada"))
        if enabled:
            self.runner.run(side_effects=False)

    def _on_run_finished(self, result) -> None:
        self.last_result = result
        self.scene.apply_statuses(result.errors, result.blocked)
        self.properties.set_statuses(result.errors, result.blocked)
        failed = len(result.errors)
        summary = f"{len(result.computed)} calculados · {len(result.cached)} en caché"
        if failed:
            summary += f" · {failed} con error"
        self.show_message(f"Ejecutado en {result.total_ms:.1f} ms — {summary}", 6000)
        if "__engine__" in result.errors:
            self.show_message(result.errors["__engine__"], 10000)
        self._update_viewer()

    def _viewer_target(self) -> str | None:
        """Nodo cuya imagen se muestra: el seleccionado, o el primer Image Viewer."""
        selected = self.scene.selected_node_ids()
        if len(selected) == 1:
            return selected[0]
        for node_id, node in self.graph.nodes.items():
            if node.type_id == "output.image_viewer":
                return node_id
        return None

    def _update_viewer(self) -> None:
        result = self.last_result
        node_id = self._viewer_target()
        if result is None or node_id is None or node_id not in self.graph.nodes:
            self.viewer.show_message(
                "Añade un Image Viewer o selecciona un nodo\ny pulsa Ejecutar."
            )
            return
        label = self.graph.node(node_id).definition.label
        if node_id in result.errors:
            self.viewer.show_message(result.errors[node_id], error=True, source=label)
        elif node_id in result.blocked:
            self.viewer.show_message(result.blocked[node_id], error=True, source=label)
        elif node_id in result.images:
            self.viewer.show_image(
                result.images[node_id], label, result.times_ms.get(node_id), result.total_ms
            )
        elif node_id in result.outputs:
            self.viewer.show_message("Este nodo no produce una imagen.", source=label)
        else:
            self.viewer.show_message("Pulsa Ejecutar para procesar el grafo.", source=label)

    def _confirm_discard(self) -> bool:
        if self.undo_stack.isClean():
            return True
        answer = QMessageBox.question(
            self,
            APP_NAME,
            "Hay cambios sin guardar y el guardado de proyectos aún no está disponible.\n"
            "¿Descartar los cambios?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def new_project(self) -> None:
        if self._confirm_discard():
            self.controller.new_graph()
            self.view.frame_all()
            self.show_message("Proyecto nuevo")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            self.scene.selectionChanged.disconnect(self._on_selection_changed)
            self.runner.shutdown()
            event.accept()
        else:
            event.ignore()
