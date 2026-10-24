"""Pruebas de la interfaz con eventos de ratón reales sobre la vista."""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from palantir_nodes.ui.editor.link_item import LinkItem
from palantir_nodes.ui.editor.node_item import NodeItem
from palantir_nodes.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, registry):
    win = MainWindow(registry)
    # pytest-qt cierra la ventana antes del teardown del fixture: sin esto aparecería
    # el diálogo modal de "descartar cambios" y la prueba se bloquearía.
    win._confirm_discard = lambda: True
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def _send(view, kind, scene_pos: QPointF, button, buttons, mods=Qt.KeyboardModifier.NoModifier):
    local = QPointF(view.mapFromScene(scene_pos))
    glob = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    event = QMouseEvent(kind, local, glob, button, buttons, mods)
    QApplication.sendEvent(view.viewport(), event)


def drag(view, start: QPointF, end: QPointF, mods=Qt.KeyboardModifier.NoModifier):
    left = Qt.MouseButton.LeftButton
    none = Qt.MouseButton.NoButton
    _send(view, QEvent.Type.MouseButtonPress, start, left, left, mods)
    mid = (start + end) / 2
    _send(view, QEvent.Type.MouseMove, mid, none, left, mods)
    _send(view, QEvent.Type.MouseMove, end, none, left, mods)
    _send(view, QEvent.Type.MouseButtonRelease, end, left, none, mods)


def socket_pos(win, node_id, name, is_output):
    return win.scene.node_items[node_id].socket(name, is_output).center()


def test_add_node_creates_item_and_undo_removes_it(window):
    node_id = window.controller.add_node("test.filter", (0, 0))
    assert isinstance(window.scene.node_items[node_id], NodeItem)
    window.undo_stack.undo()
    assert node_id not in window.scene.node_items


def test_drag_between_sockets_creates_link(window):
    ctl = window.controller
    a = ctl.add_node("test.source", (-300, 0))
    f = ctl.add_node("test.filter", (0, 0))
    drag(window.view, socket_pos(window, a, "image", True), socket_pos(window, f, "image", False))
    link = window.graph.link_to_input(f, "image")
    assert link is not None and link.src_node == a
    assert isinstance(window.scene.link_items[link.id], LinkItem)


def test_drag_from_input_to_output_also_works(window):
    ctl = window.controller
    a = ctl.add_node("test.source", (-300, 0))
    f = ctl.add_node("test.filter", (0, 0))
    drag(window.view, socket_pos(window, f, "image", False), socket_pos(window, a, "image", True))
    assert window.graph.link_to_input(f, "image") is not None


def test_drag_incompatible_does_not_connect(window):
    ctl = window.controller
    s = ctl.add_node("test.string", (-300, 0))
    f = ctl.add_node("test.filter", (0, 0))
    drag(window.view, socket_pos(window, s, "text", True), socket_pos(window, f, "amount", False))
    assert not window.graph.links


def test_detach_link_to_empty_space_removes_it(window):
    ctl = window.controller
    a = ctl.add_node("test.source", (-300, 0))
    f = ctl.add_node("test.filter", (0, 0))
    ctl.connect(a, "image", f, "image")
    start = socket_pos(window, f, "image", False)
    drag(window.view, start, start + QPointF(0, 300))
    assert not window.graph.links
    window.undo_stack.undo()
    assert window.graph.link_to_input(f, "image") is not None


def test_moving_node_updates_link_and_is_undoable(window):
    ctl = window.controller
    a = ctl.add_node("test.source", (-300, 0))
    f = ctl.add_node("test.filter", (0, 0))
    ctl.connect(a, "image", f, "image")
    item = window.scene.node_items[f]
    link_item = window.scene.link_items[window.graph.link_to_input(f, "image").id]
    before = link_item.path().pointAtPercent(1)
    header = item.scenePos() + QPointF(60, 10)
    drag(window.view, header, header + QPointF(100, 80))
    assert window.graph.node(f).position == pytest.approx((100.0, 80.0), abs=2)
    assert link_item.path().pointAtPercent(1) != before
    window.undo_stack.undo()
    assert window.graph.node(f).position == (0.0, 0.0)
    assert item.pos() == QPointF(0, 0)


def test_delete_selection_and_shift_click_multiselect(window):
    ctl = window.controller
    a = ctl.add_node("test.filter", (0, 0))
    b = ctl.add_node("test.filter", (300, 0))
    view = window.view
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    shift = Qt.KeyboardModifier.ShiftModifier
    for node_id, mods in ((a, Qt.KeyboardModifier.NoModifier), (b, shift)):
        pos = window.scene.node_items[node_id].scenePos() + QPointF(60, 10)
        _send(view, QEvent.Type.MouseButtonPress, pos, left, left, mods)
        _send(view, QEvent.Type.MouseButtonRelease, pos, left, none, mods)
    assert set(window.scene.selected_node_ids()) == {a, b}
    ctl.delete_selection()
    assert not window.graph.nodes
    window.undo_stack.undo()
    assert len(window.graph.nodes) == 2


def test_copy_paste_through_clipboard(window):
    ctl = window.controller
    a = ctl.add_node("test.source", (0, 0))
    f = ctl.add_node("test.filter", (300, 0))
    ctl.connect(a, "image", f, "image")
    window.scene.select_nodes([a, f])
    assert ctl.copy_selection() == 2
    new_ids = ctl.paste(QPointF(1000, 1000))
    assert len(new_ids) == 2
    assert len(window.graph.links) == 2
    assert set(window.scene.selected_node_ids()) == set(new_ids)


def test_properties_panel_follows_selection_and_edits(window):
    ctl = window.controller
    f = ctl.add_node("test.filter", (0, 0))
    window.scene.select_nodes([f])
    panel = window.properties
    assert panel.node_id == f
    panel._param_widgets["size"].value_changed.emit(8)
    assert window.graph.node(f).params["size"] == 8
    window.undo_stack.undo()
    assert panel._param_widgets["size"].spin.value() == 3


def test_frame_all_and_zoom(window):
    window.controller.add_node("test.filter", (2000, 2000))
    window.view.frame_all()
    center = window.view.mapToScene(window.view.viewport().rect().center())
    assert abs(center.x() - 2095) < 200 and abs(center.y() - 2000) < 300
    assert window.view.zoom <= 1.0


def test_pending_actions_are_disabled(window):
    for action in window.pending_actions.values():
        assert not action.isEnabled()
    assert window.action_new.isEnabled()


def test_new_project_clears_graph(window, monkeypatch):
    window.controller.add_node("test.filter", (0, 0))
    monkeypatch.setattr(window, "_confirm_discard", lambda: True)
    window.new_project()
    assert not window.graph.nodes and not window.scene.node_items
    assert window.undo_stack.count() == 0


def test_view_has_no_unused_point(window):
    # La conversión Shift→Ctrl conserva posición y botones.
    view = window.view
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5, 5),
        QPointF(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
    )
    out = view._shift_as_ctrl(ev)
    assert out.modifiers() & Qt.KeyboardModifier.ControlModifier
    assert not out.modifiers() & Qt.KeyboardModifier.ShiftModifier
    assert out.position().toPoint() == QPoint(5, 5)
