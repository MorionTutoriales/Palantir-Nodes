"""Parámetros conectables en el editor: sockets, campo oculto al conectar, búsqueda y proyectos."""

import json

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.ui.editor.controller import LINK_DROP_GAP
from palantir_nodes.ui.main_window import MainWindow


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


def click(win, point):
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    send(win, QEvent.Type.MouseButtonPress, point, left, left)
    send(win, QEvent.Type.MouseButtonRelease, point, left, none)


def socket_center(win, node_id, name, is_output):
    return win.scene.node_items[node_id].socket(name, is_output).center()


def field_rect(win, node_id, name):
    return win.scene.node_items[node_id].field_scene_rect(name, "param")


def make_pair(win):
    ctl = win.controller
    number = ctl.add_node("input.number", (-300, 0))
    blur = ctl.add_node("image.gaussian_blur", (100, 0))
    win.undo_stack.clear()
    return number, blur


def connect_with_mouse(win, number, blur, socket="sigma"):
    drag(win, socket_center(win, number, "value", True), socket_center(win, blur, socket, False))


# -- sockets en el nodo ------------------------------------------------------------------


def test_connectable_params_get_a_socket_and_others_do_not(win):
    blur = win.controller.add_node("image.gaussian_blur", (0, 0))
    thr = win.controller.add_node("image.threshold", (400, 0))
    item, other = win.scene.node_items[blur], win.scene.node_items[thr]
    assert set(item.input_sockets) == {"image", "ksize", "sigma"}
    assert item.socket("sigma", False).socket_type.value == "Float"
    assert item.socket("ksize", False).socket_type.value == "Integer"
    assert set(other.input_sockets) == {"image", "thresh", "maxval", "otsu"}  # 'method' es un enum
    assert other.socket("otsu", False).socket_type.value == "Boolean"


def test_value_nodes_and_sources_have_no_socket_on_their_own_value(win):
    for type_id in (
        "input.number",
        "input.integer",
        "input.boolean",
        "input.color",
        "input.vector2",
        "input.vector3",
        "input.load_video",
        "input.webcam",
    ):
        node = win.controller.add_node(type_id, (0, 0))
        assert not win.scene.node_items[node].input_sockets, type_id


def test_param_socket_sits_on_its_row_at_the_left_edge(win):
    blur = win.controller.add_node("image.gaussian_blur", (0, 0))
    item = win.scene.node_items[blur]
    for name in ("ksize", "sigma"):
        socket = item.socket(name, False).pos()
        rect = item.mapRectToScene(item._field_rect(next(r for r in item._rows if r.name == name)))
        assert socket.x() == 0 and abs(item.mapToScene(socket).y() - rect.center().y()) < 0.01


# -- conectar con el ratón ---------------------------------------------------------------


def test_connecting_hides_the_field_and_disconnecting_restores_it(win):
    number, blur = make_pair(win)
    assert field_rect(win, blur, "sigma") is not None
    connect_with_mouse(win, number, blur)
    link = win.graph.link_to_input(blur, "sigma")
    assert link is not None and link.src_node == number
    assert field_rect(win, blur, "sigma") is None  # el valor viene del nodo Number
    assert field_rect(win, blur, "ksize") is not None  # los demás campos siguen editables
    assert win.undo_stack.count() == 1

    drag(win, socket_center(win, blur, "sigma", False), QPointF(100, 400))  # soltar en vacío
    assert win.graph.link_to_input(blur, "sigma") is None
    assert field_rect(win, blur, "sigma") is not None
    assert win.graph.node(blur).params["sigma"] == 0.0  # el valor escrito se conservó


def test_clicking_a_driven_row_edits_nothing(win):
    number, blur = make_pair(win)
    win.controller.set_param(blur, "sigma", 3.0)
    connect_with_mouse(win, number, blur)
    item = win.scene.node_items[blur]
    row = next(r for r in item._rows if r.name == "sigma")
    point = item.mapToScene(QPointF(item.WIDTH / 2, row.y + item.ROW / 2))
    click(win, point)
    assert win.view.field_editor.inline is None
    drag(win, point, point + QPointF(60, 0))  # arrastrar tampoco ajusta nada
    assert win.graph.node(blur).params["sigma"] == 3.0


def test_incompatible_sockets_are_still_rejected(win):
    ctl = win.controller
    load = ctl.add_node("input.load_image", (-300, 0))
    blur = ctl.add_node("image.gaussian_blur", (100, 0))
    drag(win, socket_center(win, load, "image", True), socket_center(win, blur, "sigma", False))
    assert win.graph.link_to_input(blur, "sigma") is None  # Image -> Float


def test_conversions_apply_to_param_sockets(win):
    ctl = win.controller
    integer = ctl.add_node("input.integer", (-300, 0))
    blur = ctl.add_node("image.gaussian_blur", (100, 0))
    messages = []
    win.scene.status_message.connect(messages.append)
    drag(win, socket_center(win, integer, "value", True), socket_center(win, blur, "sigma", False))
    assert win.graph.link_to_input(blur, "sigma") is not None  # Integer -> Float


def test_replacing_a_param_connection_is_one_undoable_step(win):
    number, blur = make_pair(win)
    other = win.controller.add_node("input.number", (-300, 200))
    win.undo_stack.clear()
    connect_with_mouse(win, number, blur)
    drag(win, socket_center(win, other, "value", True), socket_center(win, blur, "sigma", False))
    assert win.graph.link_to_input(blur, "sigma").src_node == other
    assert len(win.graph.links) == 1
    win.undo_stack.undo()
    assert win.graph.link_to_input(blur, "sigma").src_node == number
    win.undo_stack.undo()
    assert win.graph.link_to_input(blur, "sigma") is None


# -- ejecución desde la ventana -----------------------------------------------------------


@pytest.fixture
def image_path(tmp_path):
    img = np.zeros((60, 80, 3), np.uint8)
    cv2.rectangle(img, (10, 10), (40, 40), (255, 255, 255), -1)
    img = cv2.add(img, np.random.default_rng(1).integers(0, 60, img.shape, dtype=np.uint8))
    path = tmp_path / "entrada.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


def test_running_uses_the_connected_value_and_follows_changes(qtbot, win, image_path):
    ctl = win.controller
    load = ctl.add_node("input.load_image", (-500, 0))
    number = ctl.add_node("input.number", (-300, 200))
    blur = ctl.add_node("image.gaussian_blur", (100, 0))
    ctl.set_param(load, "path", image_path)
    ctl.connect(load, "image", blur, "image")
    ctl.connect(number, "value", blur, "sigma")
    original = cv2.imdecode(np.fromfile(image_path, np.uint8), cv2.IMREAD_COLOR)

    for sigma in (1.0, 5.0):
        ctl.set_param(number, "value", sigma)
        with qtbot.waitSignal(win.runner.finished, timeout=5000):
            win.runner.run()
        got = win.last_result.outputs[blur]["image"]
        assert np.array_equal(got, cv2.GaussianBlur(original, (5, 5), sigma))


def test_properties_panel_disables_the_driven_widget(win):
    number, blur = make_pair(win)
    win.scene.select_nodes([blur])
    panel = win.properties
    assert panel._param_widgets["sigma"].isEnabled()
    connect_with_mouse(win, number, blur)
    win.scene.select_nodes([blur])
    assert not panel._param_widgets["sigma"].isEnabled()
    assert "proviene de otro nodo" in panel._param_widgets["sigma"].toolTip()
    assert panel._param_widgets["ksize"].isEnabled()
    win.undo_stack.undo()
    assert panel._param_widgets["sigma"].isEnabled()


# -- buscador al soltar ------------------------------------------------------------------


def popup_items(popup):
    return [popup.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(popup.list.count())]


def test_dropping_a_float_output_offers_nodes_with_float_parameters(qtbot, win):
    number = win.controller.add_node("input.number", (-300, 0))
    drag(win, socket_center(win, number, "value", True), QPointF(300, 250))
    popup = win.view.link_popup
    ids = popup_items(popup)
    assert {"image.gaussian_blur", "image.threshold", "image.canny", "image.rotate"} <= set(ids)
    assert "image.grayscale" not in ids  # sin sockets numéricos
    qtbot.keyClicks(popup.edit, "gaussian")
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)
    created = next(n for n in win.graph.nodes.values() if n.type_id == "image.gaussian_blur")
    link = next(iter(win.graph.links.values()))
    assert (link.dst_node, link.dst_socket) == (created.id, "sigma")
    socket = socket_center(win, created.id, "sigma", False)
    assert (socket.x(), socket.y()) == pytest.approx((300 + LINK_DROP_GAP, 250), abs=1.0)
    assert win.undo_stack.count() >= 1


def test_dropping_a_param_socket_offers_nodes_that_can_feed_it(qtbot, win):
    blur = win.controller.add_node("image.gaussian_blur", (300, 0))
    win.undo_stack.clear()
    drop = QPointF(-200, 250)
    drag(win, socket_center(win, blur, "ksize", False), drop)
    popup = win.view.link_popup
    ids = popup_items(popup)
    assert "input.integer" in ids and "input.number" in ids  # Integer exacto, Float por conversión
    assert ids.index("input.integer") < ids.index("input.number")
    assert "Alimentar" in popup.title.text() and "Kernel" in popup.title.text()
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)  # el primero: tipo exacto
    link = next(iter(win.graph.links.values()))
    assert (link.dst_node, link.dst_socket) == (blur, "ksize")
    assert win.graph.node(link.src_node).type_id in ids
    assert win.undo_stack.count() == 1


def test_vector_param_is_fed_by_vector_and_color_nodes(qtbot, win):
    rng = win.controller.add_node("image.in_range", (300, 0))
    drag(win, socket_center(win, rng, "lower", False), QPointF(-200, 250))
    popup = win.view.link_popup
    ids = popup_items(popup)
    assert ids.index("input.vector3") < ids.index("input.color")  # exacto antes que convertible
    qtbot.keyClicks(popup.edit, "vector3")
    qtbot.keyClick(popup.edit, Qt.Key.Key_Return)
    link = next(iter(win.graph.links.values()))
    assert win.graph.node(link.src_node).type_id == "input.vector3"
    assert link.dst_socket == "lower"


# -- proyectos y portapapeles -------------------------------------------------------------


def test_param_links_survive_save_and_open(win, tmp_path, monkeypatch):
    number, blur = make_pair(win)
    win.controller.set_param(number, "value", 4.5)
    connect_with_mouse(win, number, blur)
    path = tmp_path / "param.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    assert win.save_project()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert [(link["dst_socket"]) for link in saved["links"]] == ["sigma"]

    win.controller.new_graph()
    assert win.load_project(path)
    link = win.graph.link_to_input(blur, "sigma")
    assert link is not None and link.src_node == number
    assert field_rect(win, blur, "sigma") is None  # el campo sigue oculto tras reabrir


def test_opening_a_project_with_a_link_to_a_missing_param_socket_warns(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    number, blur = make_pair(win)
    connect_with_mouse(win, number, blur)
    path = tmp_path / "p.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    win.save_project()
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["links"][0]["dst_socket"] = "ya_no_existe"
    path.write_text(json.dumps(doc), encoding="utf-8")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    assert win.load_project(path)
    assert not win.graph.links and warnings and "inexistente" in warnings[0]


def test_copy_paste_keeps_links_to_param_sockets(win):
    number, blur = make_pair(win)
    connect_with_mouse(win, number, blur)
    win.scene.select_nodes([number, blur])
    assert win.controller.copy_selection() == 2
    pasted = win.controller.paste(QPointF(0, 500))
    assert len(pasted) == 2
    new_blur = next(i for i in pasted if win.graph.node(i).type_id == "image.gaussian_blur")
    link = win.graph.link_to_input(new_blur, "sigma")
    assert link is not None and link.src_node in pasted and link.src_node != number
    assert len(win.graph.links) == 2


def test_deleting_the_source_node_releases_the_parameter(win):
    number, blur = make_pair(win)
    connect_with_mouse(win, number, blur)
    win.controller.remove_items([number], [])
    assert win.graph.link_to_input(blur, "sigma") is None
    assert field_rect(win, blur, "sigma") is not None
    win.undo_stack.undo()
    assert win.graph.link_to_input(blur, "sigma") is not None
    assert field_rect(win, blur, "sigma") is None


# -- tiempo real --------------------------------------------------------------------------


def test_realtime_follows_a_driven_parameter(qtbot, win, video_path):
    ctl = win.controller
    load = ctl.add_node("input.load_video", (-500, 0))
    number = ctl.add_node("input.number", (-300, 250))
    thr = ctl.add_node("image.threshold", (100, 0))
    view = ctl.add_node("output.video_viewer", (400, 0))
    ctl.set_param(load, "path", video_path)
    ctl.set_param(load, "loop", True)
    ctl.set_param(number, "value", 0.0)
    ctl.connect(load, "image", thr, "image")
    ctl.connect(thr, "image", view, "image")
    ctl.connect(number, "value", thr, "thresh")
    win.runner.auto_run = True

    win.action_run.trigger()
    qtbot.waitUntil(
        lambda: win.last_result is not None and view in win.last_result.images, timeout=5000
    )
    qtbot.waitUntil(
        lambda: int(win.last_result.images[view].min()) == 255, timeout=5000
    )  # umbral 0
    ctl.set_param(number, "value", 254.0)
    qtbot.waitUntil(
        lambda: int(win.last_result.images[view].max()) == 0, timeout=5000
    )  # umbral 254
    win.runner.stop_realtime(wait=True)
