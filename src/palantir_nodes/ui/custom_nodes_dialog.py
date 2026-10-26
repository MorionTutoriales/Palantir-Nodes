"""Gestor de nodos personalizados: crear, editar, duplicar y borrar nodos escritos en Python."""

from __future__ import annotations

import html
import keyword
from collections.abc import Callable

from PySide6.QtCore import QRegularExpression, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from palantir_nodes.customnodes.analysis import Analysis, Issue
from palantir_nodes.customnodes.library import CustomNodeLibrary, CustomNodeValidationError
from palantir_nodes.customnodes.spec import CustomNodeSpec
from palantir_nodes.ui.theme import Colors

DEFAULT_CATEGORY = "Personalizados"
INDENT = "    "

TEMPLATES: dict[str, str] = {
    "Procesar una imagen": '''def mi_filtro(imagen: Image, umbral: float = 0.5) -> Image:
    """Describe aquí qué hace el nodo."""
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(gris, umbral * 255, 255, cv2.THRESH_BINARY)
    return binaria
''',
    "Calcular un valor": '''def promedio(imagen: Image) -> float:
    """Brillo medio de la imagen (0-255)."""
    return float(imagen.mean())
''',
    "Varias salidas (con nombre)": '''def separar(imagen: Image, umbral: int = 128) -> tuple[Image, int]:
    """Devuelve la máscara de los píxeles claros y cuántos hay."""
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    mascara = (gris > umbral).astype(np.uint8) * 255
    cantidad = int(cv2.countNonZero(mascara))
    return mascara, cantidad
''',
    "Entrada opcional y lista de opciones": '''def combinar(
    base: Image,
    otra: Image = None,
    modo: Literal["suma", "resta"] = "suma",
) -> Image:
    """Combina dos imágenes; la segunda es opcional."""
    if otra is None:
        return base.copy()
    otra = cv2.resize(otra, (base.shape[1], base.shape[0]))
    operacion = cv2.add if modo == "suma" else cv2.subtract
    return operacion(base, otra)
''',
}


# -- coloreado de sintaxis y editor --------------------------------------------------------


def _format(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    fmt.setFontItalic(italic)
    return fmt


class PythonHighlighter(QSyntaxHighlighter):
    """Coloreado básico de Python (palabras clave, cadenas, comentarios, números)."""

    _STATE_NONE, _STATE_DOUBLE, _STATE_SINGLE = 0, 1, 2

    def __init__(self, document) -> None:
        super().__init__(document)
        words = "|".join(sorted(keyword.kwlist, key=len, reverse=True))
        self._rules = [
            (QRegularExpression(rf"\b(?:{words})\b"), _format("#C586C0", bold=True)),
            (QRegularExpression(r"\b(?:self|cls|np|cv2|math)\b"), _format("#4EC9B0")),
            (
                QRegularExpression(r"\b(?:Image|Color|Vector2|Vector3|Any|Literal)\b"),
                _format("#4EC9B0"),
            ),
            (QRegularExpression(r"\b\d+(?:\.\d+)?\b"), _format("#B5CEA8")),
            (QRegularExpression(r"(?<=\bdef )\w+"), _format("#DCDCAA", bold=True)),
            (QRegularExpression(r"(?<=\bclass )\w+"), _format("#DCDCAA", bold=True)),
            (QRegularExpression(r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"'), _format("#CE9178")),
            (QRegularExpression(r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'"), _format("#CE9178")),
            (QRegularExpression(r"#[^\n]*"), _format("#6A9955", italic=True)),
        ]
        self._string = _format("#CE9178")

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
        self.setCurrentBlockState(self._STATE_NONE)
        if not (
            self._triple(text, '"""', self._STATE_DOUBLE)
            or self._triple(text, "'''", self._STATE_SINGLE)
        ):
            return

    def _triple(self, text: str, delimiter: str, state: int) -> bool:
        """Colorea cadenas de varias líneas (docstrings). ``True`` si el bloque queda abierto."""
        start = 0
        if self.previousBlockState() == state:
            end = text.find(delimiter)
            if end < 0:
                self.setCurrentBlockState(state)
                self.setFormat(0, len(text), self._string)
                return True
            self.setFormat(0, end + 3, self._string)
            start = end + 3
        else:
            start = text.find(delimiter)
            if start < 0:
                return False
        while start >= 0:
            end = text.find(delimiter, start + 3)
            if end < 0:
                self.setCurrentBlockState(state)
                self.setFormat(start, len(text) - start, self._string)
                return True
            self.setFormat(start, end + 3 - start, self._string)
            start = text.find(delimiter, end + 3)
        return False


class CodeEdit(QPlainTextEdit):
    """Editor de código: fuente monoespaciada, Tab = 4 espacios y sangría automática."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSizeF(10.0)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * len(INDENT))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {Colors.BASE}; color: #D4D4D4; "
            f"border: 1px solid {Colors.BORDER}; }}"
        )
        self.highlighter = PythonHighlighter(self.document())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        cursor = self.textCursor()
        if key == Qt.Key.Key_Tab and not cursor.hasSelection():
            cursor.insertText(INDENT)
            return
        if key == Qt.Key.Key_Backtab:
            self._dedent_line()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            line = cursor.block().text()[: cursor.positionInBlock()]
            indent = line[: len(line) - len(line.lstrip(" "))]
            if line.rstrip().endswith(":"):
                indent += INDENT
            super().keyPressEvent(event)
            self.textCursor().insertText(indent)
            return
        super().keyPressEvent(event)

    def _dedent_line(self) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        text = cursor.block().text()
        remove = min(len(INDENT), len(text) - len(text.lstrip(" ")))
        for _ in range(remove):
            cursor.deleteChar()


# -- presentación del análisis ---------------------------------------------------------


def analysis_html(analysis: Analysis, extra_errors: list[Issue] | None = None) -> str:
    """Resumen en HTML de lo detectado en el código (entradas, salidas, errores, avisos)."""
    esc = html.escape
    parts: list[str] = []
    if analysis.function_name:
        parts.append(
            f"<p><b>Función del nodo:</b> <code style='font-family:Consolas,monospace'>{esc(analysis.function_name)}</code></p>"
        )
        inputs = [p for p in analysis.params if p.kind == "input"]
        enums = [p for p in analysis.params if p.kind == "enum"]
        rows: list[str] = []
        for p in inputs:
            if p.optional:
                detail = f"{p.socket_type.value} — opcional (si no se conecta recibe None)"
            elif p.socket_type.value in ("Image", "Any"):
                detail = f"{p.socket_type.value} — obligatoria"
            else:
                detail = f"{p.socket_type.value} — valor por defecto <code style='font-family:Consolas,monospace'>{esc(repr(p.default))}</code>"
            rows.append(
                f"<li><code style='font-family:Consolas,monospace'>{esc(p.name)}</code>: {detail}</li>"
            )
        for p in enums:
            options = ", ".join(esc(o) for o in p.options)
            rows.append(
                f"<li><code style='font-family:Consolas,monospace'>{esc(p.name)}</code>: lista [{options}] — por defecto <code style='font-family:Consolas,monospace'>{esc(p.default)}</code></li>"
            )
        parts.append(
            "<p><b>Entradas:</b></p>"
            + (f"<ul>{''.join(rows)}</ul>" if rows else "<p><i>ninguna</i></p>")
        )
        outs = [
            f"<li><code style='font-family:Consolas,monospace'>{esc(o.name)}</code>: {o.socket_type.value}</li>"
            for o in analysis.outputs
        ]
        parts.append(
            "<p><b>Salidas:</b></p>"
            + (f"<ul>{''.join(outs)}</ul>" if outs else "<p><i>ninguna (nodo final)</i></p>")
        )
    for issue in [*analysis.errors, *(extra_errors or [])]:
        parts.append(f"<p style='color:#E0524F'>✖ {esc(str(issue))}</p>")
    for issue in analysis.warnings:
        parts.append(f"<p style='color:#D9A441'>⚠ {esc(str(issue))}</p>")
    return "".join(parts)


# -- diálogo ---------------------------------------------------------------------------------


class CustomNodesDialog(QDialog):
    """Lista de nodos personalizados y editor de su código.

    Emite ``changed(ids_modificados, ids_eliminados)`` para que la ventana adapte los nodos
    del grafo abierto. ``usage(type_id)`` dice cuántos nodos del grafo usan un tipo.
    """

    changed = Signal(list, list)
    import_paths_changed = Signal(list)  # carpetas de importación nuevas

    def __init__(
        self,
        library: CustomNodeLibrary,
        parent: QWidget | None = None,
        *,
        usage: Callable[[str], int] | None = None,
        start_new: bool = False,
        import_paths: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.library = library
        self.import_paths = list(import_paths or [])
        self._usage = usage or (lambda _id: 0)
        self.current_id: str | None = None
        self._loading = False
        self._dirty = False
        self.setWindowTitle("Nodos personalizados")
        self.resize(1080, 700)

        self.listing = QListWidget()
        self.listing.setMinimumWidth(230)
        self.btn_new = QPushButton("Nuevo")
        self.btn_duplicate = QPushButton("Duplicar")
        self.btn_delete = QPushButton("Eliminar")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nombre del nodo")
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.setToolTip("Elige una categoría o escribe una nueva")
        self.description = QLineEdit()
        self.description.setPlaceholderText(
            "Descripción (opcional; si no, se usa la primera línea del docstring)"
        )
        self.always_run = QCheckBox("Ejecutar siempre (sin caché; p. ej. si usa azar o la hora)")
        self.templates = QComboBox()
        self.templates.addItem("Plantillas…")
        self.templates.addItems(TEMPLATES)
        self.code = CodeEdit()
        self.info = QTextBrowser()
        self.info.setMaximumHeight(210)
        self.info.setStyleSheet(f"background: {Colors.PANEL}; border: 1px solid {Colors.BORDER};")
        self.btn_save = QPushButton("Guardar")
        self.btn_revert = QPushButton("Descartar cambios")
        self.btn_close = QPushButton("Cerrar")
        self.btn_paths = QPushButton("Rutas de importación…")
        self.btn_paths.setToolTip(
            "Carpetas con tus propios módulos o librerías para usar con import en el código"
        )
        self.state_label = QLabel()

        warning = QLabel(
            "⚠ El código de un nodo se ejecuta en tu equipo con tus permisos. "
            "No pegues código que no entiendas ni de origen desconocido."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #D9A441;")
        hint = QLabel(
            "El nodo es la <b>última función pública</b> del código; sus parámetros son las entradas "
            "y lo que devuelve, las salidas. Anota los tipos: <code style='font-family:Consolas,monospace'>Image, int, float, bool, str, "
            "Color, Vector2, Vector3, Literal['a','b']</code>. Ya puedes usar <code style='font-family:Consolas,monospace'>np</code>, "
            "<code style='font-family:Consolas,monospace'>cv2</code> y <code style='font-family:Consolas,monospace'>math</code>."
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setStyleSheet(f"color: {Colors.TEXT_DIM};")

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Tus nodos"))
        left_layout.addWidget(self.listing, 1)
        buttons = QHBoxLayout()
        for button in (self.btn_new, self.btn_duplicate, self.btn_delete):
            buttons.addWidget(button)
        left_layout.addLayout(buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.addRow("Nombre", self.name_edit)
        form.addRow("Categoría", self.category)
        form.addRow("Descripción", self.description)
        form.addRow("", self.always_run)
        right_layout.addLayout(form)
        right_layout.addWidget(hint)
        top = QHBoxLayout()
        top.addWidget(QLabel("Código Python"))
        top.addStretch(1)
        top.addWidget(self.templates)
        right_layout.addLayout(top)
        right_layout.addWidget(self.code, 1)
        right_layout.addWidget(self.info)
        bottom = QHBoxLayout()
        bottom.addWidget(self.state_label, 1)
        bottom.addWidget(self.btn_paths)
        for button in (self.btn_revert, self.btn_save, self.btn_close):
            bottom.addWidget(button)
        right_layout.addLayout(bottom)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addWidget(splitter, 1)

        self._analysis_timer = QTimer(self)
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.setInterval(250)
        self._analysis_timer.timeout.connect(self.refresh_analysis)

        self.listing.currentItemChanged.connect(self._on_list_selection)
        self.btn_new.clicked.connect(self.new_entry)
        self.btn_duplicate.clicked.connect(self.duplicate_current)
        self.btn_delete.clicked.connect(self.delete_current)
        self.btn_save.clicked.connect(self.save_current)
        self.btn_revert.clicked.connect(self.revert)
        self.btn_close.clicked.connect(self.close)
        self.btn_paths.clicked.connect(self.edit_import_paths)
        self.templates.activated.connect(self._on_template)
        for signal in (
            self.name_edit.textChanged,
            self.description.textChanged,
            self.category.editTextChanged,
            self.always_run.toggled,
            self.code.textChanged,
        ):
            signal.connect(self._on_edited)

        self.refresh_list()
        if start_new or not self.library.entries:
            self.new_entry(confirm=False)
        else:
            self.select_entry(self.library.ordered()[0].id, confirm=False)

    # -- rutas de importación -------------------------------------------------------------

    def edit_import_paths(self) -> bool:
        """Abre el editor de rutas de importación. ``True`` si cambiaron."""
        from palantir_nodes.ui.import_paths_dialog import ImportPathsDialog

        dialog = ImportPathsDialog(self.import_paths, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self.set_import_paths(dialog.paths())

    def set_import_paths(self, paths: list[str]) -> bool:
        if paths == self.import_paths:
            return False
        self.import_paths = list(paths)
        self.import_paths_changed.emit(list(paths))  # la ventana las aplica y las guarda
        self.refresh_analysis()  # los avisos de módulos no encontrados pueden haber cambiado
        return True

    # -- lista ---------------------------------------------------------------------------

    def refresh_list(self, select: str | None = None) -> None:
        self.listing.blockSignals(True)
        self.listing.clear()
        for spec in self.library.ordered():
            item = QListWidgetItem(f"{spec.label}  —  {spec.category}")
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            if spec.id in self.library.broken:
                item.setForeground(QColor(Colors.LINK_INVALID))
                item.setToolTip("Tiene errores: ábrelo para corregirlo")
            self.listing.addItem(item)
            if spec.id == (select or self.current_id):
                self.listing.setCurrentItem(item)
        self.listing.blockSignals(False)
        self._refresh_categories()
        self._update_buttons()

    def _refresh_categories(self) -> None:
        current = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        names = self.library.categories()
        if DEFAULT_CATEGORY not in names:
            names.append(DEFAULT_CATEGORY)
        self.category.addItems(names)
        self.category.setEditText(current or DEFAULT_CATEGORY)
        self.category.blockSignals(False)

    def _on_list_selection(self, item: QListWidgetItem | None, _previous) -> None:
        if item is None or self._loading:
            return
        type_id = item.data(Qt.ItemDataRole.UserRole)
        if type_id != self.current_id and not self.select_entry(type_id):
            self.refresh_list()  # se canceló: la lista vuelve a marcar el nodo actual

    # -- cargar y vaciar el formulario ---------------------------------------------------

    def _fill(
        self, label: str, category: str, description: str, always_run: bool, code: str
    ) -> None:
        self._loading = True
        try:
            self.name_edit.setText(label)
            self.category.setEditText(category)
            self.description.setText(description)
            self.always_run.setChecked(always_run)
            self.code.setPlainText(code)
        finally:
            self._loading = False
        self._set_dirty(False)
        self.refresh_analysis()

    def select_entry(self, type_id: str, *, confirm: bool = True) -> bool:
        """Muestra un nodo en el editor. ``False`` si el usuario canceló por cambios sin guardar."""
        if confirm and not self.confirm_discard():
            return False
        spec = self.library.get(type_id)
        if spec is None:
            return False
        self.current_id = type_id
        self._fill(spec.label, spec.category, spec.description, spec.always_run, spec.code)
        self.refresh_list(select=type_id)
        return True

    def new_entry(self, *, confirm: bool = True) -> bool:
        if confirm and not self.confirm_discard():
            return False
        self.current_id = None
        taken = {cls.label.lower() for cls in self.library.registry}
        label, n = "Nuevo nodo", 2
        while label.lower() in taken:
            label, n = f"Nuevo nodo {n}", n + 1
        self._fill(label, DEFAULT_CATEGORY, "", False, next(iter(TEMPLATES.values())))
        self._set_dirty(True)
        self.listing.blockSignals(True)
        self.listing.setCurrentItem(None)
        self.listing.blockSignals(False)
        self._update_buttons()
        return True

    # -- edición --------------------------------------------------------------------------

    def _on_edited(self, *_args) -> None:
        if self._loading:
            return
        self._set_dirty(True)
        self._analysis_timer.start()

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.state_label.setText("● Cambios sin guardar" if dirty else "")
        self._update_buttons()

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _on_template(self, index: int) -> None:
        if index <= 0:
            return
        name = self.templates.itemText(index)
        self.templates.setCurrentIndex(0)
        self.insert_template(name)

    def insert_template(self, name: str) -> bool:
        """Reemplaza el código por una plantilla (pide confirmación si ya hay código propio)."""
        template = TEMPLATES[name]
        current = self.code.toPlainText().strip()
        if current and current not in {t.strip() for t in TEMPLATES.values()}:
            answer = QMessageBox.question(
                self,
                "Plantilla",
                "Se reemplazará el código actual por la plantilla. ¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self.code.setPlainText(template)
        return True

    def current_spec(self) -> CustomNodeSpec:
        """Definición según el estado actual del formulario (sin validar)."""
        return CustomNodeSpec(
            self.current_id or "custom.nuevo",
            self.name_edit.text(),
            self.category.currentText(),
            self.code.toPlainText(),
            self.description.text().strip(),
            self.always_run.isChecked(),
        )

    def refresh_analysis(self) -> Analysis:
        issues, analysis = self.library.validate(self.current_spec())
        extra = [i for i in issues if i not in analysis.errors]
        self.info.setHtml(analysis_html(analysis, extra))
        self._last_issues = issues
        self._update_buttons()
        return analysis

    def _update_buttons(self) -> None:
        has_current = self.current_id is not None
        valid = not getattr(self, "_last_issues", [])
        self.btn_save.setEnabled(valid and self._dirty)
        self.btn_revert.setEnabled(self._dirty)
        self.btn_duplicate.setEnabled(has_current)
        self.btn_delete.setEnabled(has_current)

    # -- acciones -------------------------------------------------------------------------

    def confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Nodos personalizados",
            "Hay cambios sin guardar en este nodo. ¿Descartarlos?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def revert(self) -> None:
        if self.current_id is not None and self.library.get(self.current_id):
            self.select_entry(self.current_id, confirm=False)
        else:
            self.new_entry(confirm=False)

    def save_current(self) -> bool:
        """Valida y guarda el nodo. ``False`` si no es válido o el usuario canceló."""
        spec = self.current_spec()
        issues, analysis = self.library.validate(spec)
        if issues:
            self.info.setHtml(
                analysis_html(analysis, [i for i in issues if i not in analysis.errors])
            )
            return False
        updating = self.current_id is not None
        in_use = self._usage(self.current_id) if updating else 0
        if in_use and not self._confirm_update(spec.label, in_use):
            return False
        try:
            if updating:
                self.library.update(spec)
            else:
                spec = self.library.create(
                    spec.label, spec.category, spec.code, spec.description, spec.always_run
                )
        except CustomNodeValidationError as exc:
            self.info.setHtml(analysis_html(analysis, exc.issues))
            return False
        except OSError as exc:
            self._warn_not_saved(exc)
            if not updating:  # se aplicó en memoria aunque no se pudo escribir en disco
                spec = next(s for s in self.library.entries.values() if s.label == spec.label)
        self.current_id = spec.id
        self._set_dirty(False)
        self.refresh_list(select=spec.id)
        if updating:
            self.changed.emit([spec.id], [])
        return True

    def duplicate_current(self) -> bool:
        if self.current_id is None or not self.confirm_discard():
            return False
        try:
            spec = self.library.duplicate(self.current_id)
        except (CustomNodeValidationError, OSError) as exc:
            QMessageBox.warning(self, "Nodos personalizados", f"No se pudo duplicar:\n{exc}")
            return False
        self.select_entry(spec.id, confirm=False)
        return True

    def delete_current(self) -> bool:
        if self.current_id is None:
            return False
        spec = self.library.get(self.current_id)
        if spec is None:
            return False
        in_use = self._usage(spec.id)
        text = f"¿Eliminar el nodo «{spec.label}»? Esta acción no se puede deshacer."
        if in_use:
            text += (
                f"\n\nEl grafo abierto usa este nodo {in_use} vez/veces: "
                "esos nodos se eliminarán también (y no se podrá deshacer)."
            )
        answer = QMessageBox.question(
            self,
            "Eliminar nodo personalizado",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        removed = spec.id
        try:
            self.library.remove(removed)
        except OSError as exc:
            self._warn_not_saved(exc)
        self.current_id = None
        self.refresh_list()
        remaining = self.library.ordered()
        if remaining:
            self.select_entry(remaining[0].id, confirm=False)
        else:
            self.new_entry(confirm=False)
        self.changed.emit([], [removed])
        return True

    def _confirm_update(self, label: str, in_use: int) -> bool:
        answer = QMessageBox.question(
            self,
            "Guardar cambios",
            f"El grafo abierto usa «{label}» {in_use} vez/veces. Esos nodos se adaptarán al nuevo "
            "código: se conservan los valores cuyo nombre siga existiendo y se quitan las conexiones "
            "que ya no sean compatibles. No se podrá deshacer.\n\n¿Guardar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _warn_not_saved(self, exc: OSError) -> None:
        QMessageBox.warning(
            self,
            "Nodos personalizados",
            f"El cambio se aplicó en esta sesión pero no se pudo guardar en disco:\n{exc}",
        )

    def closeEvent(self, event) -> None:
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()

    def reject(self) -> None:
        if self.confirm_discard():
            super().reject()
