"""Ventana principal: editor central, paneles acoplables y barra superior."""

from __future__ import annotations

from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from palantir_nodes import __version__
from palantir_nodes.codegen import CodeGenerator, ExportError
from palantir_nodes.core.graph import Graph, GraphEvent
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.registry import NodeRegistry
from palantir_nodes.persistence import (
    ProjectData,
    ProjectFormatError,
    dump,
    load,
    read_project,
    write_project,
)
from palantir_nodes.ui.editor.controller import EditorController
from palantir_nodes.ui.editor.scene import NodeScene
from palantir_nodes.ui.editor.view import NodeView
from palantir_nodes.ui.properties.panel import PropertiesPanel
from palantir_nodes.ui.run_controller import RunController
from palantir_nodes.ui.viewer.panel import ViewerPanel

APP_NAME = "Palantir Nodes"

# Acciones de la barra superior que todavía no tienen implementación real.
_PENDING = {
    "prefs": ("Preferencias…", "", "Preferencias: pendiente"),
}

PROJECT_FILTER = "Proyecto de Palantir Nodes (*.json);;Todos los archivos (*)"
MAX_WARNINGS_SHOWN = 12


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
        self.project = ProjectData()
        self.project_path: Path | None = None
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
        self.runner.realtime_changed.connect(self._on_realtime_changed)
        self.runner.realtime_stopped.connect(self._on_realtime_stopped)
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

        self.action_open = QAction("Abrir proyecto…", self)
        self.action_open.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open.triggered.connect(self.open_project)
        self.action_save = QAction("Guardar", self)
        self.action_save.setShortcut(QKeySequence("Ctrl+S"))
        self.action_save.triggered.connect(self.save_project)
        self.action_save_as = QAction("Guardar como…", self)
        self.action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self.save_project_as)

        self.action_run = QAction("Ejecutar", self)
        self.action_run.setShortcut(QKeySequence("F5"))
        self.action_run.setToolTip(
            "Ejecutar (F5). Con Webcam o Load Video inicia el tiempo real; "
            "Save Image / Save Video solo escriben aquí."
        )
        self.action_run.triggered.connect(self._on_run_triggered)
        self.action_stop = QAction("Detener", self)
        self.action_stop.setShortcut(QKeySequence("Shift+F5"))
        self.action_stop.setToolTip("Detener el tiempo real y liberar cámaras y archivos")
        self.action_stop.setEnabled(False)
        self.action_stop.triggered.connect(lambda: self.runner.stop_realtime())
        self.action_pause = QAction("Pausa", self)
        self.action_pause.setShortcut(QKeySequence("F6"))
        self.action_pause.setCheckable(True)
        self.action_pause.setToolTip("Pausar o reanudar el tiempo real (F6)")
        self.action_pause.setEnabled(False)
        self.action_pause.toggled.connect(self.runner.set_paused)
        self.action_export = QAction("Exportar Python…", self)
        self.action_export.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export.setToolTip("Exportar el grafo como un script Python independiente")
        self.action_export.triggered.connect(self.export_python)
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
        file_menu.addAction(self.action_open)
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export)
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
        run_menu.addAction(self.action_pause)
        run_menu.addAction(self.action_stop)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        p = self.pending_actions
        toolbar.addAction(self.action_new)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_save)
        toolbar.addAction(self.action_save_as)
        toolbar.addSeparator()
        toolbar.addAction(self.action_run)
        toolbar.addAction(self.action_auto)
        toolbar.addAction(self.action_pause)
        toolbar.addAction(self.action_stop)
        toolbar.addSeparator()
        toolbar.addAction(self.action_export)
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

    @property
    def project_name(self) -> str:
        return self.project_path.stem if self.project_path else "Sin título"

    def _update_title(self, *_) -> None:
        dirty = "" if self.undo_stack.isClean() else " *"
        self.setWindowTitle(f"{self.project_name}{dirty} — {APP_NAME} {__version__}")

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

    def _on_run_triggered(self) -> None:
        if self.runner.realtime_active:
            return
        if self.runner.has_sources():
            self.runner.start_realtime(side_effects=True)
        else:
            self.runner.run(side_effects=True)

    def _on_realtime_changed(self, active: bool) -> None:
        self.action_run.setEnabled(not active)
        self.action_stop.setEnabled(active)
        self.action_pause.setEnabled(active)
        if not active:
            self.action_pause.blockSignals(True)
            self.action_pause.setChecked(False)
            self.action_pause.blockSignals(False)
        else:
            self.show_message("Tiempo real iniciado", 3000)

    def _on_realtime_stopped(self, reason: str) -> None:
        self.show_message(f"Tiempo real detenido: {reason}" if reason else "Tiempo real detenido")

    def _on_run_finished(self, result) -> None:
        self.last_result = result
        self.scene.apply_statuses(result.errors, result.blocked)
        self.properties.set_statuses(result.errors, result.blocked)
        failed = len(result.errors)
        if result.fps is not None:
            summary = f"Tiempo real: {result.fps:.1f} FPS · {result.total_ms:.1f} ms/fotograma"
            if failed:
                summary += f" · {failed} con error"
            self.show_message(summary, 2000)
        else:
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
            if node.type_id in ("output.image_viewer", "output.video_viewer"):
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
                result.images[node_id],
                label,
                result.times_ms.get(node_id),
                result.total_ms,
                result.fps,
            )
        elif node_id in result.outputs:
            self.viewer.show_message("Este nodo no produce una imagen.", source=label)
        else:
            self.viewer.show_message("Pulsa Ejecutar para procesar el grafo.", source=label)

    def _confirm_discard(self) -> bool:
        if self.undo_stack.isClean():
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"«{self.project_name}» tiene cambios sin guardar.\n¿Quieres guardarlos?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return self.save_project()
        return answer == buttons.Discard

    # -- proyectos ---------------------------------------------------------------------

    def _start_dir(self) -> str:
        return str(self.project_path.parent) if self.project_path else str(Path.home())

    def save_project(self) -> bool:
        """Guarda en el archivo actual (pregunta dónde si es nuevo). ``False`` si no se guardó."""
        if self.project_path is None:
            return self.save_project_as()
        return self._write_project(self.project_path)

    def save_project_as(self) -> bool:
        default = str(Path(self._start_dir()) / f"{self.project_name}.json")
        path, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", default, PROJECT_FILTER)
        if not path:
            return False
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".json")
        return self._write_project(target)

    def _write_project(self, path: Path) -> bool:
        state = self.view.state()
        self.project.name = path.stem
        self.project.auto_run = self.runner.auto_run
        self.project.zoom = state["zoom"]
        self.project.center = tuple(state["center"])
        try:
            write_project(path, dump(self.graph, self.project, __version__))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, APP_NAME, f"No se pudo guardar el proyecto:\n{exc}")
            return False
        self.project_path = path
        self.undo_stack.setClean()
        self._update_title()
        self.show_message(f"Guardado en {path}", 5000)
        return True

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir proyecto", self._start_dir(), PROJECT_FILTER
        )
        if path:
            self.load_project(Path(path))

    def load_project(self, path: Path) -> bool:
        """Carga un proyecto, reemplazando el actual. Si falla, el actual no se toca."""
        try:
            loaded, project = load(read_project(path), self.registry)
        except ProjectFormatError as exc:
            QMessageBox.critical(self, APP_NAME, f"No se pudo abrir '{Path(path).name}':\n{exc}")
            return False

        self.runner.stop_realtime(wait=True)
        self.runner.auto_run = False  # evita una ejecución por cada nodo añadido
        self.controller.new_graph()
        for node in loaded.nodes.values():
            self.graph.add_node_from_dict(node.to_dict())
        for link in loaded.links.values():
            self.graph.add_link_object(link)

        self.project, self.project_path = project, Path(path)
        self.last_result = None
        self.undo_stack.setClean()
        self.view.restore_state(project.zoom, project.center)
        self.action_auto.blockSignals(True)
        self.action_auto.setChecked(project.auto_run)
        self.action_auto.blockSignals(False)
        self.runner.auto_run = project.auto_run
        if project.auto_run:
            self.runner.run(side_effects=False)
        self._update_viewer()
        self._update_title()
        self._update_counts()
        self.show_message(f"Abierto {path}", 5000)
        if project.warnings:
            shown = project.warnings[:MAX_WARNINGS_SHOWN]
            extra = len(project.warnings) - len(shown)
            text = "\n".join(f"• {w}" for w in shown)
            if extra > 0:
                text += f"\n… y {extra} aviso(s) más"
            QMessageBox.warning(self, APP_NAME, f"El proyecto se abrió con avisos:\n\n{text}")
        return True

    def export_python(self) -> None:
        try:
            code = CodeGenerator(ExecutionPlan.from_graph(self.graph), __version__).generate()
        except ExportError as exc:
            self.scene.select_nodes([p.node_id for p in exc.problems if p.node_id])
            problems = "\n".join(f"• {p.message}" for p in exc.problems)
            QMessageBox.warning(self, APP_NAME, f"No se puede exportar el grafo:\n\n{problems}")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar a Python", "grafo.py", "Python (*.py)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(code)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"No se pudo escribir el archivo:\n{exc}")
            return
        self.show_message(f"Exportado a {path}", 8000)

    def new_project(self) -> None:
        if self._confirm_discard():
            self.runner.stop_realtime(wait=True)
            self.controller.new_graph()
            self.project, self.project_path = ProjectData(), None
            self.project.auto_run = self.runner.auto_run
            self.last_result = None
            self.undo_stack.setClean()
            self.view.frame_all()
            self._update_viewer()
            self._update_title()
            self.show_message("Proyecto nuevo")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            self.scene.selectionChanged.disconnect(self._on_selection_changed)
            self.runner.shutdown()
            event.accept()
        else:
            event.ignore()
