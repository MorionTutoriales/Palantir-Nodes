"""Aspecto de la interfaz: skins, iconos, panel de nodos, barras y paneles."""

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QColor, QDropEvent, QIcon
from PySide6.QtWidgets import QApplication, QDialog

from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.preferences import Preferences, load_preferences, preferences_path
from palantir_nodes.skins import DEFAULT_SKIN, SKINS, THEMEABLE, Skin, get_skin
from palantir_nodes.ui import icons, theme
from palantir_nodes.ui.main_window import ACTION_ICONS, VIEW_ACTION_ICONS, MainWindow
from palantir_nodes.ui.palette import NODE_MIME, NodePalette
from palantir_nodes.ui.panels import DockTitle
from palantir_nodes.ui.preferences_dialog import PreferencesDialog
from palantir_nodes.ui.theme import Colors

ORIGINAL = dict(theme._DEFAULTS)
FIXED = [name for name in ORIGINAL if name.startswith(("NODE_", "LINK_"))]


@pytest.fixture(autouse=True)
def default_skin():
    """Cada prueba empieza y termina con el skin original, que es global."""
    theme.apply_skin(DEFAULT_SKIN)
    icons.clear_cache()
    yield
    theme.apply_skin(DEFAULT_SKIN)
    icons.clear_cache()
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet("")


# -- skins (datos) ------------------------------------------------------------------------------------


def test_the_original_skin_changes_nothing_and_there_are_four():
    assert DEFAULT_SKIN == "oscuro" and SKINS["oscuro"].colors == {}
    assert list(SKINS) == ["oscuro", "medianoche", "bosque", "claro"]
    assert all(s.label and s.description for s in SKINS.values())
    assert get_skin("no_existe").id == "oscuro" and get_skin("claro").id == "claro"


def test_skins_never_touch_nodes_or_connections():
    for skin in SKINS.values():
        assert set(skin.colors) <= set(THEMEABLE)
        assert not [name for name in skin.colors if name.startswith(("NODE_", "LINK_"))]
    for forbidden in ("NODE_BODY", "NODE_TEXT", "LINK_VALID", "frame", "nada"):
        with pytest.raises(ValueError, match="no permitidos"):
            Skin("malo", "Malo", "x", {forbidden: "#000000"})


def test_every_skin_defines_valid_colours():
    for skin in SKINS.values():
        for name, value in skin.colors.items():
            assert QColor(value).isValid(), (skin.id, name)


@pytest.mark.parametrize("skin_id", list(SKINS))
def test_applying_a_skin_changes_the_interface_but_not_the_nodes(skin_id):
    theme.apply_skin(skin_id)
    for name in FIXED:
        assert getattr(Colors, name) == ORIGINAL[name], name  # nodos y conexiones intactos
    for name, value in SKINS[skin_id].colors.items():
        assert getattr(Colors, name) == value
    assert theme.current_skin().id == skin_id
    theme.apply_skin(DEFAULT_SKIN)
    assert all(getattr(Colors, name) == value for name, value in ORIGINAL.items())  # y vuelve


def test_the_default_skin_keeps_the_original_values():
    assert (Colors.WINDOW, Colors.PANEL, Colors.ACCENT, Colors.EDITOR_BG) == (
        "#2B2B2B",
        "#303030",
        "#4772B3",
        "#1D1D1D",
    )
    assert (Colors.NODE_BODY, Colors.NODE_SELECTED, Colors.LINK_VALID) == (
        "#303030",
        "#F5A623",
        "#5BD06A",
    )


def test_the_stylesheet_follows_the_skin_without_leftover_colours():
    original = theme.build_stylesheet()
    assert Colors.ACCENT in original and Colors.MENU_BG in original
    for skin_id in ("medianoche", "bosque", "claro"):
        theme.apply_skin(skin_id)
        sheet = theme.build_stylesheet()
        assert Colors.ACCENT in sheet and Colors.PANEL in sheet
        for leftover in ("#262626", "#3A3A3A", "#5E5E5E", "#CFCFCF", "#1A1A1A"):
            assert leftover not in sheet, (skin_id, leftover)  # todo sale de los colores del skin


def test_apply_theme_sets_the_palette_and_the_stylesheet(qapp):
    skin = theme.apply_theme(qapp, "medianoche")
    assert skin.id == "medianoche" and qapp.styleSheet() == theme.build_stylesheet()
    palette = qapp.palette()
    assert palette.color(palette.ColorRole.Highlight).name().upper() == Colors.ACCENT
    assert palette.color(palette.ColorRole.Window).name().upper() == Colors.WINDOW


# -- preferencias -------------------------------------------------------------------------------------


def test_preferences_store_and_validate_the_skin():
    assert Preferences().skin == "oscuro"
    loaded, warnings = Preferences.from_dict(Preferences(skin="claro").to_dict())
    assert loaded.skin == "claro" and not warnings
    loaded, warnings = Preferences.from_dict({"skin": "fantasia"})
    assert loaded.skin == "oscuro" and "fantasia" in warnings[0]
    loaded, warnings = Preferences.from_dict({"skin": 5})
    assert loaded.skin == "oscuro" and warnings


def test_preferences_dialog_offers_every_skin(qtbot):
    dialog = PreferencesDialog(Preferences(skin="bosque"))
    qtbot.addWidget(dialog)
    assert [dialog.skin.itemData(i) for i in range(dialog.skin.count())] == list(SKINS)
    assert (
        dialog.skin.currentData() == "bosque"
        and dialog.skin_note.text() == SKINS["bosque"].description
    )
    dialog.skin.setCurrentIndex(dialog.skin.findData("claro"))
    assert (
        dialog.preferences().skin == "claro"
        and dialog.skin_note.text() == SKINS["claro"].description
    )
    dialog.restore_defaults()
    assert dialog.skin.currentData() == "oscuro" and dialog.preferences().skin == "oscuro"


# -- iconos ---------------------------------------------------------------------------------------------


def source_icon_names() -> set[str]:
    """Todos los nombres entre comillas del código que coinciden con un archivo de icono."""
    files = {p.stem for p in icons.ICON_DIR.glob("*.svg")} - {"logo"}
    used = set()
    for path in Path(icons.__file__).parent.parent.rglob("*.py"):
        used |= {
            m for m in re.findall(r'"([a-z0-9-]+)"', path.read_text(encoding="utf-8")) if m in files
        }
    return used


def test_every_icon_file_renders_and_has_the_license(qapp):
    names = icons.available_icons()
    assert len(names) >= 40 and "logo" not in names
    for name in names:
        image = icons.pixmap(name, "#FFFFFF", 32).toImage()
        assert not image.isNull() and any(
            image.pixelColor(x, y).alpha() > 0 for x in range(0, 32, 2) for y in range(0, 32, 2)
        ), name
    licence = (icons.ICON_DIR / "LICENSE-lucide.txt").read_text(encoding="utf-8")
    assert licence.startswith("ISC License") and "Lucide" in licence


def test_no_unused_icons_are_bundled_and_all_used_ones_exist():
    files = {p.stem for p in icons.ICON_DIR.glob("*.svg")} - {"logo"}
    assert files == source_icon_names()
    used = (
        set(ACTION_ICONS.values())
        | set(VIEW_ACTION_ICONS.values())
        | set(icons.CATEGORY_ICONS.values())
        | {icons.DEFAULT_CATEGORY_ICON}
    )
    assert used <= files


def test_icons_are_drawn_in_the_requested_colour(qapp):
    def colours(pix):
        image = pix.toImage()
        return {
            image.pixelColor(x, y).name().upper()
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 200
        }

    assert colours(icons.pixmap("play", "#FF0000", 32)) == {"#FF0000"}
    assert colours(icons.pixmap("play", "#00FF00", 32)) == {"#00FF00"}
    default = icons.pixmap("play", size=32).toImage()
    solid = next(  # un píxel del trazo: por defecto, el color del texto (con un redondeo mínimo)
        default.pixelColor(x, y)
        for x in range(32)
        for y in range(32)
        if default.pixelColor(x, y).alpha() == 255
    )
    expected = QColor(Colors.TEXT)
    assert max(abs(solid.red() - expected.red()), abs(solid.green() - expected.green())) <= 2


def test_icon_states_use_the_skin_colours(qapp):
    icon = icons.icon("play")

    def dominant(mode, state=QIcon.State.Off):
        image = icon.pixmap(24, mode, state).toImage()
        return next(
            image.pixelColor(x, y).name().upper()
            for x in range(24)
            for y in range(24)
            if image.pixelColor(x, y).alpha() > 250
        )

    assert dominant(QIcon.Mode.Normal) == Colors.TEXT.upper()
    assert dominant(QIcon.Mode.Disabled) == Colors.DISABLED.upper()
    assert dominant(QIcon.Mode.Normal, QIcon.State.On) == Colors.ACCENT_TEXT.upper()


def test_icons_change_with_the_skin_after_clearing_the_cache(qapp):
    theme.apply_skin("claro")
    icons.clear_cache()
    after = icons.pixmap("settings", size=24).toImage()
    assert any(
        after.pixelColor(x, y).name().upper() == "#1F2430" for x in range(24) for y in range(24)
    )


def test_missing_icons_fail_clearly_and_the_logo_is_available(qapp):
    with pytest.raises(FileNotFoundError, match="no_existe"):
        icons.icon("no_existe")
    logo = icons.app_icon()
    assert not logo.isNull() and logo.pixmap(64).width() >= 32
    assert icons.category_icon_name("Imagen") == "image"
    assert icons.category_icon_name("Mi categoría") == icons.DEFAULT_CATEGORY_ICON


# -- panel de nodos ----------------------------------------------------------------------------------


@pytest.fixture
def registry():
    return load_builtin_nodes().copy()


def visible_labels(palette: NodePalette) -> list[str]:
    labels = []
    for index in range(palette.tree.topLevelItemCount()):
        top = palette.tree.topLevelItem(index)
        if top.isHidden():
            continue
        labels += [
            top.child(i).text(0) for i in range(top.childCount()) if not top.child(i).isHidden()
        ]
    return labels


def test_palette_lists_every_category_and_node(qtbot, registry):
    palette = NodePalette(registry)
    qtbot.addWidget(palette)
    groups = registry.by_category()
    assert palette.tree.topLevelItemCount() == len(groups)
    for index, (category, members) in enumerate(groups.items()):
        top = palette.tree.topLevelItem(index)
        assert top.text(0) == f"{category}  ({len(members)})" and not top.icon(0).isNull()
        assert [top.child(i).text(0) for i in range(top.childCount())] == [c.label for c in members]
    assert len(palette.visible_node_ids()) == len(registry)
    first = palette.tree.topLevelItem(0).child(0)
    assert first.toolTip(0) and first.data(0, Qt.ItemDataRole.UserRole) in registry


def test_palette_filters_by_name_category_and_description(qtbot, registry):
    palette = NodePalette(registry)
    qtbot.addWidget(palette)
    palette.search.setText("blur")
    assert set(visible_labels(palette)) == {"Gaussian Blur", "Median Blur"}
    palette.search.setText("matemáticas")  # por categoría
    assert "Add" in visible_labels(palette) and "Grayscale" not in visible_labels(palette)
    palette.search.setText("bordes")  # por descripción
    assert "Canny Edge Detection" in visible_labels(palette)
    palette.search.setText("zzz no existe")
    assert visible_labels(palette) == [] and palette.visible_node_ids() == []
    palette.search.setText("")
    assert len(palette.visible_node_ids()) == len(registry)


def test_palette_remembers_which_categories_were_open(qtbot, registry):
    palette = NodePalette(registry)
    qtbot.addWidget(palette)
    palette.show()
    by_name = {
        palette.tree.topLevelItem(i).data(
            0, Qt.ItemDataRole.UserRole + 1
        ): palette.tree.topLevelItem(i)
        for i in range(palette.tree.topLevelItemCount())
    }
    assert by_name["Imagen"].isExpanded() and not by_name["Salidas"].isExpanded()
    by_name["Salidas"].setExpanded(True)
    palette.search.setText("blur")  # filtrando se expande todo...
    palette.search.setText("")  # ...y al limpiar vuelve a como estaba
    assert by_name["Salidas"].isExpanded() and by_name["Imagen"].isExpanded()
    assert not by_name["Matemáticas"].isExpanded()


def test_palette_emits_the_chosen_node(qtbot, registry):
    palette = NodePalette(registry)
    qtbot.addWidget(palette)
    chosen = []
    palette.node_requested.connect(chosen.append)
    category = palette.tree.topLevelItem(0)
    node = category.child(0)
    palette.tree.itemDoubleClicked.emit(node, 0)
    assert chosen == [node.data(0, Qt.ItemDataRole.UserRole)]
    palette.tree.itemDoubleClicked.emit(category, 0)  # una categoría solo se abre o se cierra
    assert len(chosen) == 1
    palette.search.setText("grayscale")
    qtbot.keyClick(palette.search, Qt.Key.Key_Return)
    assert chosen[-1] == "image.grayscale"
    palette.search.setText("zzz")
    qtbot.keyClick(palette.search, Qt.Key.Key_Return)
    assert len(chosen) == 2  # sin resultados no hace nada


def test_palette_drag_carries_the_node_type(qtbot, registry):
    palette = NodePalette(registry)
    qtbot.addWidget(palette)
    item = palette.tree.topLevelItem(0).child(0)
    mime = palette.tree.mimeData([item])
    assert mime.hasFormat(NODE_MIME)
    assert bytes(mime.data(NODE_MIME)).decode() == item.data(0, Qt.ItemDataRole.UserRole)
    assert palette.tree.mimeTypes() == [NODE_MIME]
    assert bytes(palette.tree.mimeData([palette.tree.topLevelItem(0)]).data(NODE_MIME)) == b""


def test_palette_follows_the_registry(qtbot, registry):
    from palantir_nodes.libraries.manager import LibraryManager

    palette = NodePalette(registry)
    qtbot.addWidget(palette)
    manager = LibraryManager(registry)
    assert "WebSocket Server" not in palette.search.text() and not any(
        "Red" in palette.tree.topLevelItem(i).text(0)
        for i in range(palette.tree.topLevelItemCount())
    )
    manager.enable("network")
    qtbot.waitUntil(lambda: "WebSocket Server" in visible_labels_all(palette), timeout=3000)
    manager.disable("network")
    qtbot.waitUntil(lambda: "WebSocket Server" not in visible_labels_all(palette), timeout=3000)


def visible_labels_all(palette):
    return [
        palette.tree.topLevelItem(i).child(j).text(0)
        for i in range(palette.tree.topLevelItemCount())
        for j in range(palette.tree.topLevelItem(i).childCount())
    ]


def test_palette_unsubscribes_when_destroyed(qtbot, registry):
    before = len(registry._listeners)
    palette = NodePalette(registry)
    assert len(registry._listeners) == before + 1
    palette.deleteLater()
    qtbot.waitUntil(lambda: len(registry._listeners) == before, timeout=3000)
    registry.unregister("math.add")  # un cambio posterior no avisa a nadie ni falla


# -- soltar nodos y zoom en la vista --------------------------------------------------------------------


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes().copy())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def drop(view, text: str | None, at: QPointF | None = None):
    at = at or QPointF(200, 150)
    mime = QMimeData()
    if text is not None:
        mime.setData(NODE_MIME, text.encode("utf-8"))
    event = QDropEvent(
        at,
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.dropEvent(event)
    return event


def test_dropping_a_node_creates_it_where_it_was_dropped(win):
    drop(win.view, "image.grayscale", QPointF(240, 180))
    (node,) = win.graph.nodes.values()
    expected = win.view.mapToScene(240, 180)
    assert node.type_id == "image.grayscale"
    assert node.position == pytest.approx((expected.x(), expected.y()), abs=1.5)
    assert win.undo_stack.count() == 1


def test_dropping_several_nodes_cascades_them_and_ignores_garbage(win):
    drop(win.view, "image.grayscale\nimage.flip")
    nodes = list(win.graph.nodes.values())
    assert [n.type_id for n in nodes] == ["image.grayscale", "image.flip"]
    assert nodes[1].position[0] - nodes[0].position[0] == pytest.approx(28)
    before = len(win.graph.nodes)
    drop(win.view, "no.existe\n\n")
    drop(win.view, None)
    assert len(win.graph.nodes) == before


@pytest.mark.filterwarnings("ignore::DeprecationWarning")  # el constructor de Qt con QPoint
def test_view_accepts_only_node_drags(win):
    assert win.view.acceptDrops()
    from PySide6.QtGui import QDragEnterEvent

    good, bad = QMimeData(), QMimeData()
    good.setData(NODE_MIME, b"image.flip")
    bad.setText("hola")
    for mime, accepted in ((good, True), (bad, False)):
        event = QDragEnterEvent(
            QPointF(10, 10).toPoint(),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        win.view.dragEnterEvent(event)
        assert event.isAccepted() is accepted


def test_zoom_buttons_clamp_and_report(win):
    seen = []
    win.view.zoom_changed.connect(seen.append)
    win.view.set_zoom(1.0)
    win.view.zoom_by(1.25)
    assert win.view.zoom == pytest.approx(1.25) and seen[-1] == pytest.approx(1.25)
    win.view.set_zoom(99)
    assert win.view.zoom == pytest.approx(3.0)
    win.view.set_zoom(0.0001)
    assert win.view.zoom == pytest.approx(0.1)
    count = len(seen)
    win.view.set_zoom(0.1)  # sin cambio: no avisa
    assert len(seen) == count


def test_zoom_keeps_the_centre_of_the_view(win):
    win.view.set_zoom(1.0)
    win.view.centerOn(300, -120)
    before = win.view.visible_center()
    win.view.zoom_by(1.5)
    after = win.view.visible_center()
    assert (after.x(), after.y()) == pytest.approx((before.x(), before.y()), abs=1.0)


# -- ventana: barras, paneles y skins ---------------------------------------------------------------------


def test_every_action_has_an_icon(win):
    for attribute in ACTION_ICONS:
        assert not getattr(win, attribute).icon().isNull(), attribute
    for attribute in VIEW_ACTION_ICONS:
        assert not getattr(win.view, attribute).icon().isNull(), attribute
    for dock in (win.palette_dock, win.properties_dock, win.viewer_dock):
        assert not dock.toggleViewAction().icon().isNull()


def test_main_toolbar_layout_and_primary_button(win):
    toolbar = win.main_toolbar
    assert toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    run = toolbar.widgetForAction(win.action_run)
    assert run.property("primary") is True
    undo = toolbar.widgetForAction(win.action_undo)
    assert undo.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    menu = win._export_button.menu()
    assert [a.text() for a in menu.actions()] == [
        win.action_export.text(),
        win.action_compile.text(),
    ]
    assert not win._export_button.icon().isNull()
    assert not win.action_undo.isEnabled() and not win.action_stop.isEnabled()


def test_view_toolbar_sits_above_the_canvas(win):
    layout = win._central.layout()
    assert layout.itemAt(0).widget() is win.view_toolbar and layout.itemAt(1).widget() is win.view
    actions = win.view_toolbar.actions()
    for action in (win.action_grid, win.action_zoom_out, win.action_zoom_in, win.view.action_frame):
        assert action in actions


def test_view_toolbar_actions_work(win):
    win.view.set_zoom(1.0)
    win.action_zoom_in.trigger()
    assert win.view.zoom == pytest.approx(1.25) and win.action_zoom_reset.text() == "125%"
    win.action_zoom_out.trigger()
    win.action_zoom_out.trigger()
    assert win.view.zoom == pytest.approx(0.8)
    win.action_zoom_reset.trigger()
    assert win.view.zoom == pytest.approx(1.0) and win.action_zoom_reset.text() == "100%"
    assert "Zoom 100%" in win._zoom_label.text()


def test_grid_toggle_changes_the_view_and_is_remembered(win):
    assert win.action_grid.isChecked() and win.view.grid_visible
    win.action_grid.trigger()
    assert not win.view.grid_visible and win.prefs.show_grid is False
    assert load_preferences(preferences_path())[0].show_grid is False
    win.set_preferences(Preferences(**{**win.prefs.to_dict(), "show_grid": True}))
    assert win.view.grid_visible and win.action_grid.isChecked()  # el diálogo y la barra coinciden


def test_adding_nodes_from_the_palette_lands_in_the_visible_area(win, qtbot):
    win.view.centerOn(500, 300)
    win.palette.node_requested.emit("image.flip")
    win.palette.node_requested.emit("image.flip")
    first, second = list(win.graph.nodes.values())
    centre = win.view.visible_center()
    assert (
        abs(first.position[0] - (centre.x() - 95)) < 5
        and abs(first.position[1] - (centre.y() - 40)) < 5
    )
    assert second.position[0] - first.position[0] == pytest.approx(26)  # en cascada
    assert win.scene.selected_node_ids() == [second.id]
    win.palette.tree.itemDoubleClicked.emit(win.palette.tree.topLevelItem(0).child(0), 0)
    assert len(win.graph.nodes) == 3


def test_docks_have_icon_title_bars_that_close_and_float(win):
    assert win.dockWidgetArea(win.palette_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert win.dockWidgetArea(win.viewer_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    for dock, title in (
        (win.palette_dock, "Nodos"),
        (win.viewer_dock, "Visor"),
        (win.properties_dock, "Propiedades"),
    ):
        bar = dock.titleBarWidget()
        assert isinstance(bar, DockTitle) and bar.title_label.text() == title
        assert not bar.icon_label.pixmap().isNull() and not bar.btn_close.icon().isNull()
    bar = win.palette_dock.titleBarWidget()
    toggle = win.palette_dock.toggleViewAction()
    assert toggle.isChecked()
    bar.btn_close.click()
    assert not win.palette_dock.isVisible() and not toggle.isChecked()
    toggle.trigger()
    assert win.palette_dock.isVisible()
    bar.btn_float.click()
    assert win.palette_dock.isFloating()
    bar.btn_float.click()
    assert not win.palette_dock.isFloating()


def test_empty_panels_show_an_icon_and_a_hint(win):
    assert not win.viewer.empty_icon.pixmap().isNull()
    assert "Image Viewer" in win.viewer.message.text()
    win.viewer.show_message("algo falló", error=True)
    assert win.viewer._message_state == ("circle-alert", True)
    assert Colors.LINK_INVALID in win.viewer.message.styleSheet()
    from palantir_nodes.ui.panels import EmptyState

    assert win.properties._scroll.widget().findChildren(EmptyState)


def test_switching_skin_updates_colours_icons_menu_and_preferences(win):
    win.set_skin("claro")
    assert Colors.WINDOW == SKINS["claro"].colors["WINDOW"] and win._skin_id == "claro"
    assert win.prefs.skin == "claro" and load_preferences(preferences_path())[0].skin == "claro"
    assert win._skin_actions["claro"].isChecked()
    run_image = win.action_save.icon().pixmap(24).toImage()
    assert any(
        run_image.pixelColor(x, y).name().upper() == SKINS["claro"].colors["TEXT"]
        for x in range(24)
        for y in range(24)
    )
    assert Colors.EDITOR_BG in win.viewer.empty.styleSheet()
    for name in FIXED:
        assert getattr(Colors, name) == ORIGINAL[name]
    win.set_skin("no_existe")  # se ignora
    assert win._skin_id == "claro"
    win.set_skin("oscuro")
    assert Colors.WINDOW == ORIGINAL["WINDOW"] and win._skin_actions["oscuro"].isChecked()


def test_the_skin_menu_lists_all_skins_and_applies_the_choice(win):
    assert [a.text() for a in win._skin_menu.actions()] == [s.label for s in SKINS.values()]
    assert win._skin_actions["oscuro"].isChecked()
    win._skin_actions["bosque"].trigger()
    assert win._skin_id == "bosque" and win.prefs.skin == "bosque"
    assert Colors.ACCENT == SKINS["bosque"].colors["ACCENT"]


def test_switching_skin_restyles_the_application_when_it_uses_the_theme(win, qapp):
    theme.apply_theme(qapp)  # como en la aplicación real
    win.set_skin("medianoche")
    assert (
        qapp.styleSheet() == theme.build_stylesheet()
        and SKINS["medianoche"].colors["WINDOW"] in qapp.styleSheet()
    )
    palette = qapp.palette()
    assert (
        palette.color(palette.ColorRole.Window).name().upper()
        == SKINS["medianoche"].colors["WINDOW"]
    )


def test_preferences_dialog_changes_the_skin_of_the_window(win, monkeypatch):
    def fake_exec(self):
        self.skin.setCurrentIndex(self.skin.findData("medianoche"))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PreferencesDialog, "exec", fake_exec)
    win.action_prefs.trigger()
    assert win._skin_id == "medianoche" and Colors.ACCENT == SKINS["medianoche"].colors["ACCENT"]
    assert load_preferences(preferences_path())[0].skin == "medianoche"


def test_the_saved_skin_is_applied_when_the_window_opens(qtbot):
    from palantir_nodes.preferences import save_preferences

    save_preferences(Preferences(skin="bosque"))
    window = MainWindow(load_builtin_nodes().copy())
    qtbot.addWidget(window)
    assert window._skin_id == "bosque" and Colors.WINDOW == SKINS["bosque"].colors["WINDOW"]
    assert window._skin_actions["bosque"].isChecked()


def test_nodes_look_the_same_in_every_skin(win, qtbot):
    from palantir_nodes.ui.editor.node_item import NodeItem

    node_id = win.controller.add_node("image.grayscale", (0, 0))
    item = win.scene.node_items[node_id]
    snapshots = []
    for skin_id in SKINS:
        win.set_skin(skin_id)
        image = win.view.grab()
        rect = win.view.mapFromScene(item.sceneBoundingRect()).boundingRect()
        crop = image.copy(rect.adjusted(6, 6, -6, -6)).toImage()
        snapshots.append(crop.pixelColor(crop.width() // 2, 8).name())
    assert (
        isinstance(item, NodeItem) and len(set(snapshots)) == 1
    )  # el encabezado conserva su color
