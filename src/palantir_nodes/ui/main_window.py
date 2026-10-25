"""Ventana principal: editor central, paneles acoplables y barra superior."""

from __future__ import annotations

from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from palantir_nodes import __version__
from palantir_nodes.codegen import CodeGenerator, ExportError
from palantir_nodes.core.graph import Graph, GraphEvent, GraphEventKind
from palantir_nodes.customnodes.library import CustomNodeLibrary, CustomNodeValidationError
from palantir_nodes.customnodes.paths import apply_import_paths
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.libraries import available_libraries, get_library
from palantir_nodes.libraries.manager import LibraryManager
from palantir_nodes.nodes.registry import NodeRegistry
from palantir_nodes.persistence import (
    ProjectData,
    ProjectFormatError,
    dump,
    embedded_custom_nodes,
    embedded_libraries,
    load,
    read_project,
    write_project,
)
from palantir_nodes.preferences import Preferences, load_preferences, save_preferences
from palantir_nodes.ui.custom_nodes_dialog import CustomNodesDialog
from palantir_nodes.ui.editor.controller import EditorController
from palantir_nodes.ui.editor.scene import NodeScene
from palantir_nodes.ui.editor.view import NodeView
from palantir_nodes.ui.libraries_dialog import LibrariesDialog
from palantir_nodes.ui.preferences_dialog import PreferencesDialog
from palantir_nodes.ui.properties.panel import PropertiesPanel
from palantir_nodes.ui.run_controller import RunController
from palantir_nodes.ui.viewer.panel import ViewerPanel

APP_NAME = "Palantir Nodes"

PROJECT_FILTER = "Proyecto de Palantir Nodes (*.json);;Todos los archivos (*)"
MAX_WARNINGS_SHOWN = 12


class MainWindow(QMainWindow):
    def __init__(self, registry: NodeRegistry, startup_messages: list[str] | None = None) -> None:
        super().__init__()
        self.prefs, pref_warnings = load_preferences()
        self.pinned_node: str | None = None  # nodo en el que está fijado el visor
        self.libraries = LibraryManager(registry)  # librerías activas en el proyecto abierto
        self.custom_library = CustomNodeLibrary(registry)
        library_warnings = self.custom_library.load()  # registra los nodos personalizados
        startup_messages = [*(startup_messages or []), *pref_warnings, *library_warnings]
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
        self.scene.pin_requested.connect(self._toggle_pin)
        self.runner.started.connect(lambda: self.show_message("Procesando…", 0))
        self.runner.finished.connect(self._on_run_finished)
        self.runner.realtime_changed.connect(self._on_realtime_changed)
        self.runner.realtime_stopped.connect(self._on_realtime_stopped)
        self.scene.status_message.connect(self.show_message)
        self.controller.status_message.connect(self.show_message)
        self.view.zoom_changed.connect(self._update_zoom_label)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self.graph.subscribe(self._on_graph_event)
        self._apply_preferences()
        self._apply_new_project_defaults()

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
        self.action_previews = QAction("Previsualizaciones en los nodos", self)
        self.action_previews.setCheckable(True)
        self.action_previews.setChecked(True)
        self.action_previews.setToolTip("Mostrar una miniatura del resultado dentro de cada nodo")
        self.action_previews.toggled.connect(self._set_previews)
        self.action_auto = QAction("Auto", self)
        self.action_auto.setCheckable(True)
        self.action_auto.setChecked(True)
        self.action_auto.setToolTip("Ejecutar automáticamente al modificar el grafo")
        self.action_auto.toggled.connect(self._set_auto_run)

        self.action_custom_nodes = QAction("Nodos personalizados…", self)
        self.action_custom_nodes.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.action_custom_nodes.setToolTip("Crear, editar y borrar nodos escritos en Python")
        self.action_custom_nodes.triggered.connect(lambda: self.open_custom_nodes())
        self.action_new_custom_node = QAction("Nuevo nodo personalizado…", self)
        self.action_new_custom_node.triggered.connect(lambda: self.open_custom_nodes(new=True))
        self.view.new_custom_node_requested.connect(lambda: self.open_custom_nodes(new=True))
        self.action_libraries = QAction("Librerías del proyecto…", self)
        self.action_libraries.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.action_libraries.setToolTip("Activar librerías adicionales de nodos (p. ej. red)")
        self.action_libraries.triggered.connect(lambda: self.open_libraries())

        self.action_prefs = QAction("Preferencias…", self)
        self.action_prefs.setShortcut(QKeySequence("Ctrl+,"))
        self.action_prefs.setToolTip("Preferencias de la aplicación (Ctrl+,)")
        self.action_prefs.triggered.connect(self.open_preferences)

        self.action_undo = self.undo_stack.createUndoAction(self, "Deshacer")
        self.action_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.action_redo = self.undo_stack.createRedoAction(self, "Rehacer")
        self.action_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])

        self.action_quit = QAction("Salir", self)
        self.action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_quit.triggered.connect(self.close)

    def _create_menus(self) -> None:
        bar = self.menuBar()
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
        edit_menu.addAction(self.action_prefs)

        view_menu = bar.addMenu("&Ver")
        view_menu.addAction(self.view.action_frame)
        view_menu.addAction(self.action_previews)
        view_menu.addSeparator()
        view_menu.addAction(self.properties_dock.toggleViewAction())
        view_menu.addAction(self.viewer_dock.toggleViewAction())

        nodes_menu = bar.addMenu("&Nodos")
        nodes_menu.addAction(self.action_custom_nodes)
        nodes_menu.addAction(self.action_new_custom_node)
        nodes_menu.addSeparator()
        nodes_menu.addAction(self.action_libraries)

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
        toolbar.addAction(self.action_prefs)
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
        pinned = self.pinned_node
        if pinned is not None and (
            event.kind is GraphEventKind.CLEARED
            or (event.kind is GraphEventKind.NODE_REMOVED and event.node_id == pinned)
        ):
            self._set_pinned(None)

    def _toggle_pin(self, node_id: str) -> None:
        self._set_pinned(None if node_id == self.pinned_node else node_id)

    def _set_pinned(self, node_id: str | None) -> None:
        """Fija el visor en un nodo (``None`` lo suelta): deja de seguir a la selección."""
        self.pinned_node = node_id
        self.scene.set_pinned(node_id)
        self._update_viewer()
        if node_id is not None:
            self.show_message(
                "Visor fijado en este nodo (clic en la chincheta para soltarlo)", 4000
            )

    def _on_selection_changed(self) -> None:
        # La escena emite selectionChanged también mientras se destruye.
        if shiboken6.isValid(self.scene) and shiboken6.isValid(self.properties):
            nodes = self.scene.selected_node_ids()
            frames = self.scene.selected_frame_ids()
            if len(frames) == 1 and not nodes:
                self.properties.show_frame(frames[0])
            else:
                self.properties.show_selection(nodes)
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

    # -- preferencias ------------------------------------------------------------------

    def _apply_preferences(self) -> None:
        """Aplica al editor y al motor las preferencias que afectan a la sesión actual."""
        self.view.set_grid_visible(self.prefs.show_grid)
        self.view.zoom_step = self.prefs.zoom_speed
        self.runner.set_preview_rate(self.prefs.preview_rate_hz)
        apply_import_paths(self.prefs.import_paths)

    def _apply_new_project_defaults(self) -> None:
        """Estado de Auto y de las previsualizaciones para un proyecto nuevo."""
        for action, value in (
            (self.action_auto, self.prefs.auto_run_default),
            (self.action_previews, self.prefs.previews_default),
        ):
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)
        self.runner.auto_run = self.prefs.auto_run_default
        self.runner.set_previews(self.prefs.previews_default)
        self.project.auto_run = self.prefs.auto_run_default
        self.project.previews = self.prefs.previews_default

    def open_preferences(self) -> None:
        dialog = PreferencesDialog(self.prefs, self)
        dialog.custom_nodes_requested.connect(self.open_custom_nodes)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_preferences(dialog.preferences())

    def set_preferences(self, prefs: Preferences) -> bool:
        """Aplica y guarda las preferencias. ``False`` si no se pudieron guardar."""
        self.prefs = prefs
        self._apply_preferences()
        return self._save_preferences(warn=True)

    def _save_preferences(self, *, warn: bool) -> bool:
        try:
            save_preferences(self.prefs)
        except OSError as exc:
            if warn:
                QMessageBox.warning(
                    self, APP_NAME, f"No se pudieron guardar las preferencias:\n{exc}"
                )
            return False
        return True

    def _remember_project(self, path: Path) -> None:
        if self.prefs.last_project != str(path):
            self.prefs.last_project = str(path)
            self._save_preferences(warn=False)  # recordar el último proyecto no es crítico

    def reopen_last_project(self) -> bool:
        """Abre el último proyecto si la preferencia está activada y el archivo existe."""
        if not (self.prefs.reopen_last_project and self.prefs.last_project):
            return False
        path = Path(self.prefs.last_project)
        return path.is_file() and self.load_project(path)

    def _set_previews(self, enabled: bool) -> None:
        self.runner.set_previews(enabled)
        if enabled:
            if not self.runner.realtime_active:
                self.runner.run(side_effects=False)  # recalcula para tener miniaturas
        else:
            self.scene.apply_previews({})

    def _on_run_finished(self, result) -> None:
        self.last_result = result
        if result.previews is not None:  # None = no se calcularon en este fotograma
            self.scene.apply_previews(result.previews)
        self.scene.apply_texts(self._node_texts(result))
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

    def _node_texts(self, result) -> dict[str, str]:
        """Texto que muestra cada nodo de texto (String Viewer) en este resultado."""
        texts: dict[str, str] = {}
        for node_id, node in self.graph.nodes.items():
            name = node.definition.shows_text
            value = result.inputs.get(node_id, {}).get(name) if name else None
            if value is not None and node_id not in result.errors and node_id not in result.blocked:
                texts[node_id] = str(value)
        return texts

    def _viewer_target(self) -> str | None:
        """Nodo cuya imagen se muestra: el fijado, el seleccionado o el primer Image Viewer."""
        if self.pinned_node in self.graph.nodes:
            return self.pinned_node
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
        if node_id == self.pinned_node:
            label += " (fijado)"
        if node_id in result.errors:
            self.viewer.show_message(result.errors[node_id], error=True, source=label)
        elif node_id in result.blocked:
            self.viewer.show_message(result.blocked[node_id], error=True, source=label)
        elif self.graph.node(node_id).definition.shows_text and node_id in result.inputs:
            name = self.graph.node(node_id).definition.shows_text
            self.viewer.show_text(str(result.inputs[node_id].get(name, "")), label)
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
        self.project.previews = self.runner.preview_enabled
        self.project.pinned_node = self.pinned_node
        self.project.libraries = self.libraries.enabled
        self.project.zoom = state["zoom"]
        self.project.center = tuple(state["center"])
        try:
            write_project(
                path,
                dump(self.graph, self.project, __version__, self._custom_nodes_for_project()),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, APP_NAME, f"No se pudo guardar el proyecto:\n{exc}")
            return False
        self.project_path = path
        self.undo_stack.setClean()
        self._update_title()
        self._remember_project(path)
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
        previous_libraries = self.libraries.enabled
        try:
            data = read_project(path)
            leftovers, import_notes = self._import_embedded_custom_nodes(data)
            library_ids, library_warnings = embedded_libraries(data)
            unknown = self.libraries.set_enabled(library_ids)  # antes de crear los nodos
            loaded, project = load(data, self.registry)
        except ProjectFormatError as exc:
            self.libraries.set_enabled(previous_libraries)
            QMessageBox.critical(self, APP_NAME, f"No se pudo abrir '{Path(path).name}':\n{exc}")
            return False
        project.custom_nodes = leftovers  # los que no se importaron se conservan al guardar
        project.libraries = self.libraries.enabled
        project.warnings[:0] = [
            *import_notes,
            *library_warnings,
            *(
                f"La librería '{i}' no existe en esta versión (sus nodos se conservan)"
                for i in unknown
            ),
            *self._missing_package_notes(),
        ]

        self.runner.stop_realtime(wait=True)
        self.runner.auto_run = False  # evita una ejecución por cada nodo añadido
        self.controller.new_graph()
        for node in loaded.nodes.values():
            self.graph.add_node_from_dict(node.to_dict())
        for link in loaded.links.values():
            self.graph.add_link_object(link)
        for frame in loaded.frames.values():
            self.graph.add_frame(frame)

        self.project, self.project_path = project, Path(path)
        self.pinned_node = None
        self._set_pinned(project.pinned_node if project.pinned_node in self.graph.nodes else None)
        self.last_result = None
        self.undo_stack.setClean()
        self.view.restore_state(project.zoom, project.center)
        self.action_auto.blockSignals(True)
        self.action_auto.setChecked(project.auto_run)
        self.action_auto.blockSignals(False)
        self.action_previews.blockSignals(True)
        self.action_previews.setChecked(project.previews)
        self.action_previews.blockSignals(False)
        self.runner.set_previews(project.previews)
        self.runner.auto_run = project.auto_run
        if project.auto_run:
            self.runner.run(side_effects=False)
        self._update_viewer()
        self._update_title()
        self._update_counts()
        self._remember_project(Path(path))
        self.show_message(f"Abierto {path}", 5000)
        if project.warnings:
            shown = project.warnings[:MAX_WARNINGS_SHOWN]
            extra = len(project.warnings) - len(shown)
            text = "\n".join(f"• {w}" for w in shown)
            if extra > 0:
                text += f"\n… y {extra} aviso(s) más"
            QMessageBox.warning(self, APP_NAME, f"El proyecto se abrió con avisos:\n\n{text}")
        return True

    # -- librerías adicionales ---------------------------------------------------------

    def _library_usage(self) -> dict[str, int]:
        """Cuántos nodos del grafo abierto pertenecen a cada librería."""
        return {
            library.id: sum(self._count_nodes_of_type(cls.type_id) for cls in library.nodes)
            for library in available_libraries()
        }

    def _missing_package_notes(self) -> list[str]:
        """Avisos de las librerías activas a las que les faltan paquetes por instalar."""
        notes = []
        for library_id in self.libraries.enabled:
            library = get_library(library_id)
            if library is not None and library.missing:
                notes.append(
                    f"La librería '{library.label}' necesita instalar: {library.install_command}"
                )
        return notes

    def open_libraries(self) -> None:
        """Muestra el diálogo de librerías y aplica la selección al proyecto."""
        dialog = LibrariesDialog(self.libraries.enabled, self, usage=self._library_usage())
        if dialog.exec() == LibrariesDialog.DialogCode.Accepted:
            self.apply_libraries(dialog.selected_ids())

    def apply_libraries(self, selected: list[str]) -> bool:
        """Activa y desactiva librerías. Al desactivar una en uso se piden confirmación y se
        eliminan sus nodos del grafo. ``False`` si el usuario canceló o no hubo cambios."""
        removed = [i for i in self.libraries.enabled if i not in selected]
        added = [i for i in selected if i not in self.libraries.enabled]
        if not removed and not added:
            return False
        usage = self._library_usage()
        doomed = sum(usage.get(i, 0) for i in removed)
        if doomed:
            names = ", ".join(get_library(i).label for i in removed if usage.get(i, 0))
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"El grafo abierto usa nodos de: {names}.\n\nSi las desactivas se eliminarán "
                f"{doomed} nodo(s) (y no se podrá deshacer). ¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self.runner.stop_realtime(wait=True)  # las conexiones abiertas se cierran
        for library_id in removed:
            for type_id in self.libraries.type_ids(library_id):
                self.graph.remove_nodes_of_type(type_id)
        self.libraries.set_enabled(selected)
        self.project.libraries = self.libraries.enabled
        self.undo_stack.clear()  # los comandos anteriores ya no corresponden al grafo
        self.undo_stack.resetClean()  # el proyecto cambió: hay cambios sin guardar
        self.last_result = None
        self._update_viewer()
        self._update_title()
        self._update_counts()
        self.show_message("Librerías del proyecto: " + (", ".join(selected) or "ninguna"), 5000)
        return True

    # -- nodos personalizados ----------------------------------------------------------

    def _count_nodes_of_type(self, type_id: str) -> int:
        return len(self.graph.nodes_of_type(type_id))

    def open_custom_nodes(self, new: bool = False) -> None:
        """Abre el gestor de nodos personalizados (``new``: empieza creando uno)."""
        dialog = CustomNodesDialog(
            self.custom_library,
            self,
            usage=self._count_nodes_of_type,
            start_new=new,
            import_paths=self.prefs.import_paths,
        )
        dialog.changed.connect(self._on_custom_nodes_changed)
        dialog.import_paths_changed.connect(self._on_import_paths_changed)
        dialog.exec()

    def _on_import_paths_changed(self, paths: list[str]) -> None:
        """Aplica y guarda las carpetas de importación de los nodos personalizados."""
        self.prefs.import_paths = list(paths)
        apply_import_paths(paths)
        self.runner.clear_cache()  # los nodos que fallaron por un import deben reintentarse
        self._save_preferences(warn=True)

    def _on_custom_nodes_changed(self, changed: list[str], removed: list[str]) -> None:
        """Adapta el grafo abierto cuando se edita o se borra un nodo personalizado en uso."""
        notes: list[str] = []
        affected = False
        for type_id in changed:
            if self.graph.nodes_of_type(type_id):
                notes += self.graph.migrate_node_type(type_id)
                affected = True
        for type_id in removed:
            if self.graph.remove_nodes_of_type(type_id):
                affected = True
        if not affected:
            return
        self.undo_stack.clear()  # los comandos anteriores ya no corresponden al grafo
        self.undo_stack.resetClean()  # el grafo cambió: hay cambios sin guardar
        self.last_result = None
        self._update_viewer()
        self._update_title()
        self._update_counts()
        if notes:
            shown = notes[:MAX_WARNINGS_SHOWN]
            text = "\n".join(f"• {n}" for n in shown)
            if len(notes) > len(shown):
                text += f"\n… y {len(notes) - len(shown)} más"
            QMessageBox.warning(self, APP_NAME, f"Se adaptó el grafo al nodo modificado:\n\n{text}")

    def _custom_nodes_for_project(self) -> list[dict]:
        """Definiciones que se guardan en el proyecto: las que usa el grafo y las pendientes."""
        used: dict[str, dict] = {}
        for node in self.graph.nodes.values():
            spec = self.custom_library.get(node.type_id)
            if spec is not None:
                used[spec.id] = spec.to_dict()
        for raw in self.project.custom_nodes:  # traídas por el archivo y sin importar
            used.setdefault(raw["id"], raw)
        return list(used.values())

    def _import_embedded_custom_nodes(self, data: dict) -> tuple[list[dict], list[str]]:
        """Ofrece importar los nodos personalizados que trae un proyecto.

        Devuelve las definiciones que quedaron sin importar y avisos para mostrar al abrir.
        """
        specs, _ = embedded_custom_nodes(data)
        library = self.custom_library
        notes: list[str] = []
        pending = [s for s in specs if s.id not in library.entries]
        for spec in specs:
            known = library.entries.get(spec.id)
            if known is not None and known.code != spec.code:
                notes.append(
                    f"El proyecto trae otra versión de '{spec.label}'; se usa la de tu biblioteca"
                )
        if not pending:
            return [], notes
        names = ", ".join(sorted(s.label for s in pending))
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Este proyecto incluye {len(pending)} nodo(s) personalizado(s) con código Python: "
            f"{names}.\n\nSi los importas, ese código se ejecutará en tu equipo con tus permisos. "
            "Impórtalos solo si confías en el origen del proyecto.\n\n"
            "¿Importarlos a tu biblioteca de nodos?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            notes.append(
                "No se importaron los nodos personalizados: sus nodos se conservan sin mostrarse"
            )
            return [s.to_dict() for s in pending], notes
        leftovers: list[dict] = []
        for spec in pending:
            try:
                library.import_spec(spec)
            except CustomNodeValidationError as exc:
                leftovers.append(spec.to_dict())
                notes.append(f"No se pudo importar '{spec.label}': {exc.issues[0]}")
            except OSError:
                notes.append(f"'{spec.label}' se importó pero no se pudo guardar en tu biblioteca")
        return leftovers, notes

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
            self.libraries.set_enabled([])  # cada proyecto activa las suyas
            self.project, self.project_path = ProjectData(), None
            self._apply_new_project_defaults()
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
