"""Arrastrar un socket y soltarlo en vacío: buscador filtrado por compatibilidad."""

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from palantir_nodes.core.graph import Graph
from palantir_nodes.core.types import SocketType as T
from palantir_nodes.core.types import is_compatible
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui.editor.controller import LINK_DROP_GAP
from palantir_nodes.ui.editor.node_item import NodeItem, socket_offset
from palantir_nodes.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def registry():
    return load_builtin_nodes()


def by_label(matches):
    return {m.node_type.label: m for m in matches}


# -- consulta de compatibilidad (sin Qt) -------------------------------------------------


def test_image_output_matches_image_inputs_with_the_best_socket(registry):
    matches = by_label(registry.compatible_with(T.IMAGE, origin_is_output=True))
    assert {"Grayscale", "Gaussian Blur", "Image Viewer", "Save Video"} <= set(matches)
    assert not {"Number", "Load Image", "Webcam", "Add", "Find Contours"} & {
        n for n in matches if n in ("Number", "Load Image", "Webcam", "Add")
    }
    assert matches["Blend Images"].socket == "image_a"  # el primer socket de imagen
    assert matches["Merge Channels"].socket == "blue"
    assert matches["Draw Contours"].socket == "image"  # y no 'contours' (Any)
    assert all(m.exact for m in matches.values())


def test_float_output_matches_float_inputs_only(registry):
    matches = by_label(registry.compatible_with(T.FLOAT, origin_is_output=True))
    assert matches["Add"].socket == "a" and matches["Blend Images"].socket == "factor"
    assert matches["Add Weighted"].socket == "alpha"
    assert "Grayscale" not in matches and "Image Viewer" not in matches


def test_convertible_types_rank_after_exact_ones(registry):
    ints = registry.compatible_with(T.INTEGER, origin_is_output=True)
    assert ints and not any(m.exact for m in ints)  # no hay entradas Integer
    assert by_label(ints)["Add"].rank == 1 and by_label(ints)["Add"].socket == "a"
    assert by_label(ints)["Draw Contours"].rank == 2  # una entrada Any acepta de todo
    assert [m.rank for m in ints] == sorted(m.rank for m in ints)  # convertibles antes que Any
    flags = registry.compatible_with(T.BOOLEAN, origin_is_output=True)
    assert flags and not any(m.exact for m in flags)
    assert {m.rank for m in flags} == {1, 2}
    floats = registry.compatible_with(T.FLOAT, origin_is_output=False)  # desde una entrada Float
    ranks = [m.rank for m in floats]
    assert ranks == sorted(ranks) and 0 in ranks and 1 in ranks
    labels = by_label(floats)
    assert labels["Number"].rank == 0 and labels["Integer"].rank == 1


def test_any_output_only_reaches_any_inputs(registry):
    matches = registry.compatible_with(T.ANY, origin_is_output=True)
    assert [m.node_type.label for m in matches] == ["Draw Contours"]
    assert matches[0].socket == "contours" and matches[0].exact


def test_any_input_accepts_every_output_with_exact_first(registry):
    matches = registry.compatible_with(T.ANY, origin_is_output=False)
    assert matches[0].node_type.label == "Find Contours" and matches[0].exact
    assert all(m.rank == 2 for m in matches[1:])
    assert by_label(matches)["Load Image"].socket == "image"
    assert "Image Viewer" not in by_label(matches)  # sin salidas


def test_image_input_matches_image_outputs(registry):
    matches = by_label(registry.compatible_with(T.IMAGE, origin_is_output=False))
    assert {"Load Image", "Grayscale", "Webcam", "Split Channels"} <= set(matches)
    assert "Number" not in matches and "Image Viewer" not in matches
    assert matches["Threshold"].socket == "image"  # y no 'threshold' (Float)


def test_results_are_sorted_by_rank_then_name(registry):
    for socket_type in T:
        for origin_is_output in (True, False):
            matches = registry.compatible_with(socket_type, origin_is_output=origin_is_output)
            keys = [(m.rank, m.node_type.label.lower()) for m in matches]
            assert keys == sorted(keys)


def test_everything_offered_can_really_connect_and_nothing_connectable_is_missing(registry):
    """Comprobación exhaustiva contra el validador de conexiones del grafo."""
    types = list(registry)
    for origin_cls in types:
        for is_output, specs in ((True, origin_cls.outputs), (False, origin_cls.inputs)):
            for spec in specs:
                matches = {
                    m.node_type.type_id: m
                    for m in registry.compatible_with(spec.type, origin_is_output=is_output)
                }
                for other in types:
                    graph = Graph(registry)
                    a = graph.add_node(origin_cls.type_id)
                    b = graph.add_node(other.type_id)
                    candidates = other.inputs if is_output else other.outputs
                    connectable = [
                        c
                        for c in candidates
                        if (
                            graph.can_connect(a.id, spec.name, b.id, c.name)
                            if is_output
                            else graph.can_connect(b.id, c.name, a.id, spec.name)
                        )
                    ]
                    if other.type_id in matches:
                        chosen = matches[other.type_id].socket
                        assert chosen in {c.name for c in connectable}, (
                            origin_cls.label,
                            spec.name,
                            other.label,
                            chosen,
                        )
                    else:
                        assert not connectable, (origin_cls.label, spec.name, other.label)
    assert is_compatible(T.IMAGE, T.IMAGE)  # el validador y la consulta usan la misma regla


# -- posición del nodo nuevo -------------------------------------------------------------


def test_socket_offset_matches_the_real_node_item(qapp, registry):
    graph = Graph(registry)
    for cls in registry:
        item = NodeItem(graph.add_node(cls.type_id))
        for spec in cls.outputs:
            pos = item.socket(spec.name, True).pos()
            assert socket_offset(cls, spec.name, is_output=True) == (pos.x(), pos.y()), cls.label
        for spec in cls.inputs:
            pos = item.socket(spec.name, False).pos()
            assert socket_offset(cls, spec.name, is_output=False) == (pos.x(), pos.y()), cls.label
    with pytest.raises(KeyError):
        socket_offset(registry.require("image.grayscale"), "nada", is_output=True)


# -- interfaz con ratón real -------------------------------------------------------------


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def send(win, kind, scene_pos, button, buttons):
    view = win.view
    local = QPointF(view.mapFromScene(scene_pos))
    glob = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    event = QMouseEvent(kind, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), event)


def drag(win, start, end):
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    send(win, QEvent.Type.MouseButtonPress, start, left, left)
    send(win, QEvent.Type.MouseMove, (start + end) / 2, none, left)
    send(win, QEvent.Type.MouseMove, end, none, left)
    send(win, QEvent.Type.MouseButtonRelease, end, left, none)


def socket_center(win, node_id, name, is_output):
    return win.scene.node_items[node_id].socket(name, is_output).center()


def popup_items(popup):
    return [popup.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(popup.list.count())]


def drop_from(win, node_id, socket, is_output, drop):
    drag(win, socket_center(win, node_id, socket, is_output), drop)
    return win.view.link_popup


def test_dropping_an_output_in_empty_space_opens_a_filtered_search(qtbot, win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    popup = drop_from(win, load, "image", True, QPointF(300, 250))
    assert popup is not None and popup.isVisible()
    ids = popup_items(popup)
    assert ids[0] != "" and "image.grayscale" in ids and "output.image_viewer" in ids
    assert "input.number" not in ids and "math.add" not in ids  # sin entrada de imagen
    assert "Image" in popup.title.text() and "Conectar" in popup.title.text()
    assert "→ entrada" in popup.list.item(0).text()
    assert len(win.graph.nodes) == 1 and not win.graph.links  # aún no se ha creado nada


def test_choosing_creates_the_node_connected_and_placed_at_the_drop_point(qtbot, win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    win.undo_stack.clear()
    drop = QPointF(300, 250)
    popup = drop_from(win, load, "image", True, drop)
    qtbot.keyClicks(popup.edit, "gauss")
    assert popup_items(popup) == ["image.gaussian_blur"]  # el filtro respeta la compatibilidad
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)

    assert len(win.graph.nodes) == 2 and len(win.graph.links) == 1
    new_id = next(i for i in win.graph.nodes if i != load)
    link = next(iter(win.graph.links.values()))
    assert (link.src_node, link.src_socket) == (load, "image")
    assert (link.dst_node, link.dst_socket) == (new_id, "image")
    socket = socket_center(win, new_id, "image", False)  # su entrada queda junto al cursor
    assert (socket.x(), socket.y()) == pytest.approx((drop.x() + LINK_DROP_GAP, drop.y()), abs=1.0)
    assert win.scene.selected_node_ids() == [new_id]

    assert win.undo_stack.count() == 1  # nodo y conexión, un solo paso
    win.undo_stack.undo()
    assert len(win.graph.nodes) == 1 and not win.graph.links
    win.undo_stack.redo()
    assert len(win.graph.nodes) == 2 and next(iter(win.graph.links.values())).id == link.id


def test_escape_cancels_without_changes(qtbot, win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    win.undo_stack.clear()
    popup = drop_from(win, load, "image", True, QPointF(300, 250))
    qtbot.keyClick(popup.edit, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: win.view.link_popup is None, timeout=3000)
    assert len(win.graph.nodes) == 1 and not win.graph.links and win.undo_stack.count() == 0


def test_dropping_an_input_searches_nodes_that_can_feed_it(qtbot, win):
    gray = win.controller.add_node("image.grayscale", (300, 0))
    win.undo_stack.clear()
    drop = QPointF(-200, 250)
    popup = drop_from(win, gray, "image", False, drop)
    ids = popup_items(popup)
    assert "input.load_image" in ids and "image.canny" in ids and "input.number" not in ids
    assert "Alimentar" in popup.title.text() and "← salida" in popup.list.item(0).text()
    qtbot.keyClicks(popup.edit, "load image")
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)

    new_id = next(i for i in win.graph.nodes if i != gray)
    link = next(iter(win.graph.links.values()))
    assert (link.src_node, link.src_socket) == (new_id, "image")
    assert (link.dst_node, link.dst_socket) == (gray, "image")
    socket = socket_center(win, new_id, "image", True)  # su salida queda a la izquierda
    assert (socket.x(), socket.y()) == pytest.approx((drop.x() - LINK_DROP_GAP, drop.y()), abs=1.0)
    assert win.undo_stack.count() == 1


def test_float_output_connects_to_the_float_socket(qtbot, win):
    number = win.controller.add_node("input.number", (-300, 0))
    popup = drop_from(win, number, "value", True, QPointF(300, 0))
    ids = popup_items(popup)
    assert "compose.blend" in ids and "image.grayscale" not in ids
    qtbot.keyClicks(popup.edit, "blend")
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)
    link = next(iter(win.graph.links.values()))
    assert link.dst_socket == "factor"


def test_implicit_conversion_is_offered_after_exact_matches(qtbot, win):
    integer = win.controller.add_node("input.integer", (-300, 0))
    popup = drop_from(win, integer, "value", True, QPointF(300, 0))
    qtbot.keyClicks(popup.edit, "add weighted")
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)
    link = next(iter(win.graph.links.values()))
    assert link.dst_socket == "alpha"  # Integer → Float, con conversión implícita


def test_any_output_only_offers_nodes_with_any_inputs(qtbot, win):
    contours = win.controller.add_node("image.find_contours", (-300, 0))
    popup = drop_from(win, contours, "contours", True, QPointF(300, 0))
    assert popup_items(popup) == ["image.draw_contours"]
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)  # Enter elige el primero de la lista
    assert next(iter(win.graph.links.values())).dst_socket == "contours"


def test_arrow_keys_move_the_selection_before_enter(qtbot, win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    popup = drop_from(win, load, "image", True, QPointF(300, 0))
    ids = popup_items(popup)
    qtbot.keyClick(popup.edit, Qt.Key.Key_Down)
    qtbot.keyClick(popup.edit, Qt.Key.Key_Down)
    qtbot.keyClick(popup.edit, Qt.Key.Key_Up)
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)
    created = next(n for n in win.graph.nodes.values() if n.id != load)
    assert created.type_id == ids[1]


def test_clicking_a_result_with_the_mouse_also_works(qtbot, win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    popup = drop_from(win, load, "image", True, QPointF(300, 0))
    qtbot.keyClicks(popup.edit, "flip")
    popup._choose_item(popup.list.item(0))
    assert any(n.type_id == "image.flip" for n in win.graph.nodes.values())


def test_dropping_on_a_node_body_does_not_open_the_search(win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    other = win.controller.add_node("image.canny", (300, 0))
    messages = []
    win.scene.status_message.connect(messages.append)
    body = win.scene.node_items[other].scenePos() + QPointF(95, 12)  # encabezado, sin socket
    assert drop_from(win, load, "image", True, body) is None
    assert any("socket" in m for m in messages)
    assert not win.graph.links


def test_dropping_on_a_socket_still_connects_directly(win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    gray = win.controller.add_node("image.grayscale", (300, 0))
    assert drop_from(win, load, "image", True, socket_center(win, gray, "image", False)) is None
    assert win.graph.link_to_input(gray, "image") is not None


def test_dragging_an_existing_link_off_an_input_still_removes_it(win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    gray = win.controller.add_node("image.grayscale", (300, 0))
    win.controller.connect(load, "image", gray, "image")
    popup = drop_from(win, gray, "image", False, QPointF(300, 400))
    assert popup is None and not win.graph.links


def test_empty_space_inside_a_frame_or_under_a_link_counts_as_empty(qtbot, win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    win.controller.add_frame(200, 150, 400, 300)
    popup = drop_from(win, load, "image", True, QPointF(400, 300))  # dentro del cuerpo del frame
    assert popup is not None
    qtbot.keyClick(popup.edit, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: win.view.link_popup is None, timeout=3000)


def test_no_compatible_node_reports_instead_of_opening_an_empty_list(win, monkeypatch):
    load = win.controller.add_node("input.load_image", (-300, 0))
    messages = []
    win.controller.status_message.connect(messages.append)
    monkeypatch.setattr(win.registry, "compatible_with", lambda *a, **k: [])
    assert drop_from(win, load, "image", True, QPointF(300, 0)) is None
    assert messages and "compatible" in messages[0]


def test_the_new_node_is_a_normal_node_afterwards(qtbot, win):
    load = win.controller.add_node("input.load_image", (-300, 0))
    popup = drop_from(win, load, "image", True, QPointF(300, 0))
    qtbot.keyClicks(popup.edit, "gauss")
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)
    new_id = next(i for i in win.graph.nodes if i != load)
    win.controller.set_param(new_id, "ksize", 9)  # se puede editar
    win.controller.delete_selection()  # y eliminar
    assert new_id not in win.graph.nodes and not win.graph.links
