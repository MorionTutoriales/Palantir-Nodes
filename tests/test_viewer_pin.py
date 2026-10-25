"""Chincheta de los nodos con imagen: deja fijo el visor aunque cambie la selección."""

import json

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from palantir_nodes.nodes.registry import load_builtin_nodes
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


def click_at(win, scene_pos):
    view = win.view
    local = QPointF(view.mapFromScene(scene_pos))
    glob = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    for kind, button, buttons in (
        (QEvent.Type.MouseButtonPress, left, left),
        (QEvent.Type.MouseButtonRelease, left, none),
    ):
        QApplication.sendEvent(
            view.viewport(),
            QMouseEvent(kind, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier),
        )


def click_pin(win, node_id):
    item = win.scene.node_items[node_id]
    click_at(win, item.mapToScene(item.pin_rect().center()))


@pytest.fixture
def graph_with_images(win, tmp_path, qtbot):
    img_a = np.full((10, 12, 3), 40, np.uint8)
    img_b = np.full((10, 12, 3), 200, np.uint8)
    paths = []
    for name, img in (("a.png", img_a), ("b.png", img_b)):
        path = tmp_path / name
        cv2.imencode(".png", img)[1].tofile(str(path))
        paths.append(str(path))
    ctl = win.controller
    a = ctl.add_node("input.load_image", (0, 0))
    b = ctl.add_node("input.load_image", (300, 0))
    ctl.set_param(a, "path", paths[0])
    ctl.set_param(b, "path", paths[1])
    number = ctl.add_node("input.number", (0, 300))
    win.runner.run(side_effects=False)
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=10000)
    return win, a, b, number


def test_only_nodes_with_images_get_a_pin(win):
    ctl = win.controller
    pins = {
        label: win.scene.node_items[ctl.add_node(type_id, (0, 0))].pinnable
        for label, type_id in {
            "load": "input.load_image",
            "blur": "image.gaussian_blur",
            "viewer": "output.image_viewer",
            "save": "output.save_image",
            "number": "input.number",
            "slider": "input.slider",
            "contours": "image.find_contours",
        }.items()
    }
    assert pins == {
        "load": True,
        "blur": True,
        "viewer": True,  # sin salidas pero recibe una imagen
        "save": True,
        "number": False,
        "slider": False,
        "contours": False,  # recibe una imagen pero entrega contornos y un conteo
    }


def test_clicking_the_pin_pins_and_unpins_without_moving_the_node(graph_with_images):
    win, a, b, number = graph_with_images
    item = win.scene.node_items[a]
    start = item.pos()
    click_pin(win, a)
    assert win.pinned_node == a and item.pinned and not win.scene.node_items[b].pinned
    assert item.pos() == start
    click_pin(win, a)
    assert win.pinned_node is None and not item.pinned


def test_pinning_another_node_moves_the_pin(graph_with_images):
    win, a, b, _ = graph_with_images
    click_pin(win, a)
    click_pin(win, b)
    assert win.pinned_node == b
    assert win.scene.node_items[b].pinned and not win.scene.node_items[a].pinned


def test_pinned_viewer_ignores_the_selection(graph_with_images):
    win, a, b, number = graph_with_images
    click_pin(win, a)
    for node_id in (b, number, None):
        win.scene.select_nodes([node_id] if node_id else [])
        assert win._viewer_target() == a
    assert win.viewer.source.text().endswith("(fijado)")
    click_pin(win, a)
    win.scene.select_nodes([b])
    assert win._viewer_target() == b  # al soltarla vuelve a seguir la selección


def test_without_a_pin_the_viewer_follows_the_selection(graph_with_images):
    win, a, b, _ = graph_with_images
    win.scene.select_nodes([a])
    assert win._viewer_target() == a
    win.scene.select_nodes([b])
    assert win._viewer_target() == b


def test_deleting_the_pinned_node_releases_the_pin(graph_with_images):
    win, a, b, _ = graph_with_images
    click_pin(win, a)
    win.graph.remove_node(a)
    assert win.pinned_node is None and win.scene.pinned_id is None
    win.scene.select_nodes([b])
    assert win._viewer_target() == b


def test_new_project_and_clearing_release_the_pin(graph_with_images):
    win, a, _, _ = graph_with_images
    click_pin(win, a)
    win.new_project()
    assert win.pinned_node is None


def test_pin_survives_undo_of_unrelated_edits_and_node_rebuilds(graph_with_images):
    win, a, b, _ = graph_with_images
    click_pin(win, a)
    win.scene._rebuild()  # p. ej. al editar un nodo personalizado
    assert win.scene.node_items[a].pinned


def test_pin_is_saved_and_restored_with_the_project(graph_with_images, tmp_path, qtbot):
    win, a, b, _ = graph_with_images
    click_pin(win, b)
    path = tmp_path / "p.json"
    assert win._write_project(path)
    assert json.loads(path.read_text(encoding="utf-8"))["editor"]["pinned_node"] == b
    other = MainWindow(load_builtin_nodes())
    other._confirm_discard = lambda: True
    qtbot.addWidget(other)
    assert other.load_project(path)
    assert other.pinned_node == b and other.scene.node_items[b].pinned


def test_project_pinning_a_missing_node_is_ignored(graph_with_images, tmp_path, qtbot):
    win, a, _, _ = graph_with_images
    path = tmp_path / "p.json"
    win._write_project(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["editor"]["pinned_node"] = "no-existe"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert win.load_project(path) and win.pinned_node is None
    data["editor"]["pinned_node"] = 7  # tipo incorrecto
    path.write_text(json.dumps(data), encoding="utf-8")
    assert win.load_project(path) and win.pinned_node is None


def test_the_pin_does_not_break_painting_or_field_editing(graph_with_images):
    win, a, _, _ = graph_with_images
    click_pin(win, a)
    assert not win.view.grab().isNull()
    item = win.scene.node_items[a]
    assert item.pin_rect().right() < item.WIDTH - 18  # no pisa el aviso de error de la esquina
