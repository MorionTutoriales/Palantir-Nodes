"""Frames (grupos visuales de nodos): modelo, deshacer, ratón real y persistencia."""

import json

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QInputDialog

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.errors import GraphError
from palantir_nodes.core.graph import (
    FRAME_MIN_HEIGHT,
    FRAME_MIN_WIDTH,
    Frame,
    Graph,
    GraphEventKind,
)
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.persistence import ProjectData, dump, load
from palantir_nodes.ui.editor.controller import FRAME_PADDING, FRAME_TITLE_HEIGHT
from palantir_nodes.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def registry():
    return load_builtin_nodes()


@pytest.fixture
def g(registry):
    return Graph(registry)


# -- modelo ------------------------------------------------------------------------------


def test_add_update_remove_frame_emits_events(g):
    events = []
    g.subscribe(events.append)
    g.add_frame(Frame("f1", "Entradas", "#336699", 10, 20, 300, 200))
    g.update_frame("f1", title="  Otro  ", x=50)
    frame = g.frame("f1")
    assert (frame.title, frame.x, frame.color) == ("Otro", 50.0, "#336699")
    g.update_frame("f1", x=50)  # sin cambio: sin evento
    g.remove_frame("f1")
    assert [e.kind for e in events] == [
        GraphEventKind.FRAME_ADDED,
        GraphEventKind.FRAME_CHANGED,
        GraphEventKind.FRAME_REMOVED,
    ]
    assert all(e.frame_id == "f1" for e in events)
    assert not g.frames


@pytest.mark.parametrize(
    "fields",
    [
        {"title": ""},
        {"title": "   "},
        {"title": 5},
        {"color": "rojo"},
        {"color": "#12345"},
        {"color": "#GGGGGG"},
        {"x": float("nan")},
        {"y": float("inf")},
        {"width": "ancho"},
        {"x": True},
        {"desconocido": 1},
    ],
)
def test_invalid_frame_fields_are_rejected(g, fields):
    g.add_frame(Frame("f"))
    before = g.frame("f").to_dict()
    with pytest.raises(GraphError):
        g.update_frame("f", **fields)
    assert g.frame("f").to_dict() == before


def test_frame_size_is_clamped_to_minimum(g):
    g.add_frame(Frame("f", width=10, height=5))
    assert (g.frame("f").width, g.frame("f").height) == (FRAME_MIN_WIDTH, FRAME_MIN_HEIGHT)
    g.update_frame("f", width=1, height=1)
    assert (g.frame("f").width, g.frame("f").height) == (FRAME_MIN_WIDTH, FRAME_MIN_HEIGHT)


def test_color_is_normalized_and_duplicates_rejected(g):
    g.add_frame(Frame("f", color="#abcdef"))
    assert g.frame("f").color == "#ABCDEF"
    with pytest.raises(GraphError, match="Ya existe"):
        g.add_frame(Frame("f"))
    with pytest.raises(GraphError, match="No existe"):
        g.remove_frame("nada")


def test_graph_stores_a_copy_and_clear_removes_frames(g):
    original = Frame("f", "A")
    stored = g.add_frame(original)
    original.title = "cambiado fuera"
    assert g.frame("f").title == "A" and stored is g.frame("f")
    g.clear()
    assert not g.frames


def test_frames_do_not_affect_execution_or_export(g, registry):
    load_node = g.add_node("input.load_image", params={"path": "x.png"})
    view = g.add_node("output.image_viewer")
    g.add_link(load_node.id, "image", view.id, "image")
    code_before = CodeGenerator(ExecutionPlan.from_graph(g)).generate()
    plan_before = ExecutionPlan.from_graph(g)
    g.add_frame(Frame("f", x=-50, y=-50, width=900, height=600))
    assert CodeGenerator(ExecutionPlan.from_graph(g)).generate() == code_before
    plan_after = ExecutionPlan.from_graph(g)
    assert plan_after.order == plan_before.order and plan_after.incoming == plan_before.incoming


# -- persistencia ------------------------------------------------------------------------


def test_frames_roundtrip_through_project_file(g, registry):
    g.add_node("image.grayscale", (10, 10))
    g.add_frame(Frame("a", "Entrada ñ", "#112233", -5, 6, 400, 300))
    g.add_frame(Frame("b", "Salida", "#FFAA00", 500, 0, 120, 90))
    graph2, project = load(json.loads(json.dumps(dump(g, ProjectData(), ""))), registry)
    assert [f.to_dict() for f in graph2.frames.values()] == [f.to_dict() for f in g.frames.values()]
    assert not project.warnings


def test_old_projects_without_frames_still_load(registry):
    doc = {"format": "palantir-nodes", "version": 1, "nodes": [], "links": []}
    graph2, project = load(doc, registry)
    assert not graph2.frames and not project.warnings


def test_invalid_frames_in_file_are_skipped_or_repaired(registry):
    good = {
        "id": "ok",
        "title": "Bien",
        "color": "#101010",
        "x": 1,
        "y": 2,
        "width": 200,
        "height": 100,
    }
    doc = {
        "format": "palantir-nodes",
        "version": 1,
        "nodes": [],
        "links": [],
        "frames": [
            good,
            "no soy objeto",
            {"title": "sin id", "x": 0, "y": 0, "width": 100, "height": 100},
            {"id": "pos", "x": "a", "y": 0, "width": 100, "height": 100},
            {"id": "ok", "x": 0, "y": 0, "width": 100, "height": 100},  # id duplicado
            {"id": "fix", "title": "", "color": "azul", "x": 0, "y": 0, "width": 5, "height": 5},
        ],
    }
    graph2, project = load(doc, registry)
    assert set(graph2.frames) == {"ok", "fix"}
    fix = graph2.frame("fix")
    assert (fix.title, fix.color) == ("Frame", "#4A6FA5")
    assert (fix.width, fix.height) == (FRAME_MIN_WIDTH, FRAME_MIN_HEIGHT)
    assert len(project.warnings) == 6


def test_frames_must_be_a_list(registry):
    from palantir_nodes.persistence import ProjectFormatError

    doc = {"format": "palantir-nodes", "version": 1, "nodes": [], "links": [], "frames": {}}
    with pytest.raises(ProjectFormatError, match="frames"):
        load(doc, registry)


# -- interfaz ----------------------------------------------------------------------------


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def send(view, kind, scene_pos, button, buttons):
    local = QPointF(view.mapFromScene(scene_pos))
    glob = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    event = QMouseEvent(kind, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), event)


def drag(win, start, delta):
    view = win.view
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    send(view, QEvent.Type.MouseButtonPress, start, left, left)
    send(view, QEvent.Type.MouseMove, start + delta / 2, none, left)
    send(view, QEvent.Type.MouseMove, start + delta, none, left)
    send(view, QEvent.Type.MouseButtonRelease, start + delta, left, none)


def title_point(win, frame_id):
    item = win.scene.frame_items[frame_id]
    return item.scenePos() + QPointF(60, FRAME_TITLE_HEIGHT / 2)


def handle_point(win, frame_id):
    item = win.scene.frame_items[frame_id]
    rect = item.scene_rect()
    return QPointF(rect.right() - 6, rect.bottom() - 6)


def node_pos(win, node_id):
    return win.graph.node(node_id).position


def test_add_frame_creates_item_and_undo_removes_it(win):
    frame_id = win.controller.add_frame(100, 50)
    assert frame_id in win.scene.frame_items and win.graph.frame(frame_id).x == 100
    assert win.scene.selected_frame_ids() == [frame_id]
    win.undo_stack.undo()
    assert frame_id not in win.scene.frame_items and not win.graph.frames
    win.undo_stack.redo()
    assert frame_id in win.scene.frame_items


def test_frame_selection_wraps_selected_nodes(win):
    ctl = win.controller
    a = ctl.add_node("image.grayscale", (0, 0))
    b = ctl.add_node("image.canny", (400, 200))
    win.scene.select_nodes([a, b])
    frame_id = ctl.frame_selection()
    frame = win.graph.frame(frame_id)
    rect = (
        win.scene.node_items[a]
        .sceneBoundingRect()
        .united(win.scene.node_items[b].sceneBoundingRect())
    )
    assert frame.x == pytest.approx(rect.left() - FRAME_PADDING)
    assert frame.y == pytest.approx(rect.top() - FRAME_PADDING - FRAME_TITLE_HEIGHT)
    assert frame.width == pytest.approx(rect.width() + 2 * FRAME_PADDING)
    assert frame.height == pytest.approx(rect.height() + 2 * FRAME_PADDING + FRAME_TITLE_HEIGHT)
    assert win.scene.frame_items[frame_id].scene_rect().contains(rect)


def test_frame_selection_without_nodes_explains(win):
    messages = []
    win.controller.status_message.connect(messages.append)
    assert win.controller.frame_selection() is None
    assert messages and "Selecciona nodos" in messages[0]
    assert not win.graph.frames


def test_dragging_title_moves_contained_nodes_only(win):
    ctl = win.controller
    inside = ctl.add_node("image.grayscale", (20, 40))
    inside2 = ctl.add_node("image.canny", (250, 60))
    outside = ctl.add_node("image.flip", (900, 40))
    straddling = ctl.add_node("image.erode", (480, 40))  # sobresale del borde derecho
    link_ok = ctl.connect(inside, "image", inside2, "image")
    assert link_ok
    frame_id = ctl.add_frame(0, 0, 520, 300)
    stack_before = win.undo_stack.count()
    before = {n: node_pos(win, n) for n in (inside, inside2, outside, straddling)}

    drag(win, title_point(win, frame_id), QPointF(130, 70))

    frame = win.graph.frame(frame_id)
    assert (frame.x, frame.y) == pytest.approx((130, 70), abs=1.0)
    for node in (inside, inside2):
        assert node_pos(win, node) == pytest.approx(
            (before[node][0] + 130, before[node][1] + 70), abs=1.0
        )
    assert node_pos(win, outside) == before[outside]
    assert node_pos(win, straddling) == before[straddling]
    # las conexiones siguen a los nodos
    link = next(iter(win.graph.links.values()))
    path = win.scene.link_items[link.id].path()
    assert path.pointAtPercent(0).x() > before[inside][0] + 100

    assert win.undo_stack.count() == stack_before + 1  # un solo paso
    win.undo_stack.undo()
    assert (win.graph.frame(frame_id).x, win.graph.frame(frame_id).y) == (0.0, 0.0)
    assert {n: node_pos(win, n) for n in before} == before
    assert win.scene.node_items[inside].pos() == QPointF(*before[inside])


def test_dragging_frame_with_selected_node_inside_registers_one_step(win):
    ctl = win.controller
    node = ctl.add_node("image.grayscale", (30, 50))
    frame_id = ctl.add_frame(0, 0, 400, 300)
    win.scene.select_nodes([node])
    win.scene.frame_items[frame_id].setSelected(True)
    stack_before = win.undo_stack.count()
    drag(win, title_point(win, frame_id), QPointF(60, 40))
    assert win.undo_stack.count() == stack_before + 1
    assert node_pos(win, node) == pytest.approx((90, 90), abs=1.0)
    win.undo_stack.undo()
    assert node_pos(win, node) == (30.0, 50.0)


def test_nested_frame_moves_with_outer_frame(win):
    ctl = win.controller
    inner_node = ctl.add_node("image.grayscale", (60, 90))
    outer = ctl.add_frame(0, 0, 600, 400)
    inner = ctl.add_frame(40, 50, 300, 200)
    drag(win, title_point(win, outer), QPointF(100, 25))
    assert (win.graph.frame(inner).x, win.graph.frame(inner).y) == pytest.approx((140, 75), abs=1.0)
    assert node_pos(win, inner_node) == pytest.approx((160, 115), abs=1.0)
    win.undo_stack.undo()
    assert (win.graph.frame(inner).x, win.graph.frame(inner).y) == (40.0, 50.0)


def test_dragging_the_body_does_not_move_the_frame(win):
    frame_id = win.controller.add_frame(0, 0, 400, 300)
    body = win.scene.frame_items[frame_id].scenePos() + QPointF(200, 150)
    stack_before = win.undo_stack.count()
    drag(win, body, QPointF(80, 80))
    frame = win.graph.frame(frame_id)
    assert (frame.x, frame.y) == (0.0, 0.0) and win.undo_stack.count() == stack_before


def test_clicking_inside_frame_still_selects_nodes(win):
    node = win.controller.add_node("image.grayscale", (50, 60))
    win.controller.add_frame(0, 0, 500, 300)
    win.scene.clearSelection()
    item = win.scene.node_items[node]
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    point = item.scenePos() + QPointF(50, 10)
    send(win.view, QEvent.Type.MouseButtonPress, point, left, left)
    send(win.view, QEvent.Type.MouseButtonRelease, point, left, none)
    assert win.scene.selected_node_ids() == [node] and not win.scene.selected_frame_ids()


def test_resize_with_handle_and_minimum_size(win):
    frame_id = win.controller.add_frame(0, 0, 300, 200)
    node = win.controller.add_node("image.grayscale", (20, 40))
    before = node_pos(win, node)
    drag(win, handle_point(win, frame_id), QPointF(120, 80))
    frame = win.graph.frame(frame_id)
    assert (frame.width, frame.height) == pytest.approx((420, 280), abs=1.0)
    assert (frame.x, frame.y) == (0.0, 0.0) and node_pos(win, node) == before
    drag(win, handle_point(win, frame_id), QPointF(-2000, -2000))
    frame = win.graph.frame(frame_id)
    assert (frame.width, frame.height) == (FRAME_MIN_WIDTH, FRAME_MIN_HEIGHT)
    win.undo_stack.undo()
    assert win.graph.frame(frame_id).width == pytest.approx(420, abs=1.0)
    win.undo_stack.undo()
    assert win.graph.frame(frame_id).width == 300.0


def test_delete_frame_keeps_nodes_and_undo_restores_it(win):
    node = win.controller.add_node("image.grayscale", (20, 40))
    frame_id = win.controller.add_frame(0, 0, 300, 200)
    win.scene.select_frames([frame_id])
    win.controller.delete_selection()
    assert not win.graph.frames and node in win.graph.nodes
    assert frame_id not in win.scene.frame_items
    win.undo_stack.undo()
    assert win.graph.frame(frame_id).width == 300.0 and frame_id in win.scene.frame_items


def test_edit_title_and_color_with_undo_and_validation(win):
    frame_id = win.controller.add_frame(0, 0)
    messages = []
    win.controller.status_message.connect(messages.append)
    win.controller.edit_frame(frame_id, title="Procesado", color="#00ff00")
    assert win.graph.frame(frame_id).title == "Procesado"
    assert win.graph.frame(frame_id).color == "#00FF00"
    assert win.scene.frame_items[frame_id].title == "Procesado"
    count = win.undo_stack.count()
    win.controller.edit_frame(frame_id, color="verde")  # inválido: no se aplica
    assert win.undo_stack.count() == count and messages
    win.controller.edit_frame(frame_id, title="Procesado")  # sin cambio: nada que deshacer
    assert win.undo_stack.count() == count
    win.undo_stack.undo()
    assert win.graph.frame(frame_id).title == "Frame"


def test_rename_via_double_click_dialog(win, monkeypatch):
    frame_id = win.controller.add_frame(0, 0)
    answers = [("Mi grupo", True), ("", True), ("Ignorado", False)]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: answers.pop(0))

    left = Qt.MouseButton.LeftButton
    point = title_point(win, frame_id)
    send(win.view, QEvent.Type.MouseButtonDblClick, point, left, left)
    assert win.graph.frame(frame_id).title == "Mi grupo"
    win.scene.frame_rename_requested.emit(frame_id)  # título vacío: se ignora
    win.scene.frame_rename_requested.emit(frame_id)  # cancelado
    assert win.graph.frame(frame_id).title == "Mi grupo"


def test_properties_panel_shows_and_edits_frame(win):
    frame_id = win.controller.add_frame(10, 20, 300, 200)
    panel = win.properties
    assert panel.frame_id == frame_id  # el frame recién creado queda seleccionado
    assert panel._frame_title.text() == "Frame"
    panel._frame_title.setText("Desde el panel")
    panel._frame_title.editingFinished.emit()
    assert win.graph.frame(frame_id).title == "Desde el panel"
    win.undo_stack.undo()
    assert panel._frame_title.text() == "Frame"  # el panel sigue al modelo
    win.controller.edit_frame(frame_id, width=500)
    assert "500" in panel._frame_info.text()
    win.scene.select_frames([])
    assert panel.frame_id is None


def test_removing_the_shown_frame_resets_the_panel(win):
    frame_id = win.controller.add_frame(0, 0)
    win.undo_stack.undo()
    assert win.properties.frame_id is None and frame_id not in win.graph.frames


def test_frames_survive_save_and_open(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    node = win.controller.add_node("image.grayscale", (20, 40))
    win.scene.select_nodes([node])
    frame_id = win.controller.frame_selection("Grupo ñ")
    expected = win.graph.frame(frame_id).to_dict()
    path = tmp_path / "con_frames.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    assert win.save_project()
    assert json.loads(path.read_text(encoding="utf-8"))["frames"][0]["title"] == "Grupo ñ"

    win.controller.new_graph()
    assert not win.scene.frame_items
    assert win.load_project(path)
    assert [f.to_dict() for f in win.graph.frames.values()] == [expected]
    assert frame_id in win.scene.frame_items and win.undo_stack.isClean()


def test_adding_frame_marks_project_dirty(win):
    win.undo_stack.setClean()
    win.controller.add_frame(0, 0)
    assert not win.undo_stack.isClean()
