"""Previsualización de imágenes dentro de los nodos."""

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QImage, QPainter

from palantir_nodes.core.graph import Graph
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.engine.realtime import RealtimeSession
from palantir_nodes.engine.thumbnails import PREVIEW_MAX, make_thumbnail
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.persistence import ProjectData, dump, load
from palantir_nodes.ui.editor.node_item import PREVIEW_GAP, PREVIEW_HEIGHT, PREVIEW_WIDTH
from palantir_nodes.ui.main_window import MainWindow
from palantir_nodes.ui.realtime_worker import RealtimeWorker

# -- miniaturas (sin Qt) -----------------------------------------------------------------


@pytest.mark.parametrize(
    "shape,expected",
    [
        ((480, 640, 3), (160, 213, 3)),  # apaisada: limita el alto
        ((640, 480, 3), (160, 120, 3)),  # vertical
        ((1080, 1920), (144, 256)),  # gris, limita el ancho
        ((100, 120, 4), (100, 120, 4)),  # pequeña: no se amplía
        ((3, 2000, 3), (1, 256, 3)),  # extrema: nunca queda en 0
    ],
)
def test_thumbnail_keeps_aspect_and_never_upscales(shape, expected):
    thumb = make_thumbnail(np.zeros(shape, np.uint8), *PREVIEW_MAX)
    assert thumb.shape == expected and thumb.dtype == np.uint8


def test_thumbnail_is_an_independent_copy():
    original = np.full((20, 30, 3), 7, np.uint8)
    original.flags.writeable = False
    small = make_thumbnail(original, 256, 160)
    assert small is not original and small.flags.writeable
    small[:] = 99
    assert int(original.max()) == 7


@pytest.fixture(scope="module")
def registry():
    return load_builtin_nodes()


@pytest.fixture
def image_path(tmp_path):
    img = np.zeros((300, 400, 3), np.uint8)
    img[:, :200] = (40, 200, 60)  # mitad izquierda verde
    path = tmp_path / "imagen ñ.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


def chain(g, image_path):
    load_node = g.add_node("input.load_image", params={"path": image_path})
    gray = g.add_node("image.grayscale")
    view = g.add_node("output.image_viewer")
    number = g.add_node("input.number")
    g.add_link(load_node.id, "image", gray.id, "image")
    g.add_link(gray.id, "image", view.id, "image")
    return load_node.id, gray.id, view.id, number.id


def test_executor_previews_only_when_requested(registry, image_path):
    g = Graph(registry)
    load_id, gray_id, view_id, number_id = chain(g, image_path)
    plan = ExecutionPlan.from_graph(g)
    assert Executor().run(plan, ExecContext()).previews is None

    result = Executor().run(plan, ExecContext(preview_max=(256, 160)))
    assert set(result.previews) == {load_id, gray_id, view_id}  # solo nodos con imagen
    assert number_id not in result.previews
    assert result.previews[load_id].shape == (160, 213, 3)
    assert result.previews[gray_id].ndim == 2
    assert result.previews[view_id].shape == result.previews[gray_id].shape


def test_failed_nodes_have_no_preview(registry):
    g = Graph(registry)
    broken = g.add_node("input.load_image", params={"path": "no_existe.png"})
    gray = g.add_node("image.grayscale")
    g.add_link(broken.id, "image", gray.id, "image")
    result = Executor().run(ExecutionPlan.from_graph(g), ExecContext(preview_max=(256, 160)))
    assert result.previews == {}  # calculadas, pero ningún nodo tiene imagen


def test_realtime_session_limits_preview_rate(registry, tmp_path):
    video = tmp_path / "v.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (64, 48))
    for _ in range(8):
        writer.write(np.full((48, 64, 3), 90, np.uint8))
    writer.release()
    g = Graph(registry)
    load_node = g.add_node("input.load_video", params={"path": str(video)})
    view = g.add_node("output.video_viewer")
    g.add_link(load_node.id, "image", view.id, "image")

    session = RealtimeSession(ExecutionPlan.from_graph(g))
    try:
        assert session.step().previews is None  # desactivadas por defecto
        session.preview_size = (256, 160)
        session.preview_interval = 3600.0  # solo la primera
        first = session.step()
        later = [session.step() for _ in range(3)]
        assert set(first.previews) == {load_node.id, view.id}
        assert all(r.previews is None for r in later)
        session.preview_interval = 0.0  # todas
        assert all(session.step().previews is not None for _ in range(3))
    finally:
        session.close()


def test_worker_keeps_previews_when_replacing_an_unread_result():
    from palantir_nodes.engine.executor import ExecutionResult

    worker = RealtimeWorker(ExecutionPlan(), True, (256, 160))
    with_previews = ExecutionResult()
    with_previews.previews = {"n": np.zeros((4, 4), np.uint8)}
    worker._publish(with_previews)
    worker._publish(ExecutionResult())  # fotograma sin miniaturas (limitado)
    taken = worker.take()
    assert taken.previews is not None and "n" in taken.previews
    worker._publish(ExecutionResult())
    assert worker.take().previews is None  # nada que conservar


# -- NodeItem ----------------------------------------------------------------------------


@pytest.fixture
def win(qtbot):
    window = MainWindow(load_builtin_nodes())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def test_set_preview_grows_the_node_and_none_restores_it(win):
    node = win.controller.add_node("image.grayscale", (0, 0))
    item = win.scene.node_items[node]
    base = item.height
    sockets = {n: s.pos() for n, s in {**item.input_sockets, **item.output_sockets}.items()}
    assert not item.has_preview and item.preview_rect() is None

    item.set_preview(np.full((120, 240, 3), 90, np.uint8))  # 2:1
    rect = item.preview_rect()
    assert item.has_preview
    assert rect.width() == pytest.approx(PREVIEW_WIDTH) and rect.height() == pytest.approx(86)
    assert item.height == pytest.approx(base + rect.height() + PREVIEW_GAP)
    assert rect.bottom() <= item.height and rect.left() >= 0 and rect.right() <= item.WIDTH
    assert {n: s.pos() for n, s in {**item.input_sockets, **item.output_sockets}.items()} == sockets

    item.set_preview(None)
    assert not item.has_preview and item.height == base
    item.set_preview(None)  # idempotente


def test_preview_fits_portrait_tiny_and_tall_images(win):
    item = win.scene.node_items[win.controller.add_node("image.grayscale", (0, 0))]
    item.set_preview(np.zeros((300, 100), np.uint8))  # vertical: manda el alto
    assert item.preview_rect().height() == pytest.approx(PREVIEW_HEIGHT)
    assert item.preview_rect().width() == pytest.approx(PREVIEW_HEIGHT / 3)
    item.set_preview(np.zeros((8, 8), np.uint8))  # diminuta: se amplía como mucho 3 veces
    assert item.preview_rect().width() == pytest.approx(24)
    item.set_preview(np.zeros((20, 40, 4), np.uint8))  # con alfa
    assert item.has_preview


def test_preview_is_actually_painted(win):
    node = win.controller.add_node("image.grayscale", (0, 0))
    item = win.scene.node_items[node]
    green = np.zeros((100, 200, 3), np.uint8)
    green[:] = (0, 255, 0)  # BGR
    item.set_preview(green)
    rect = item.preview_rect()
    scene_rect = item.mapRectToScene(QRectF(-4, -4, item.WIDTH + 8, item.height + 8))
    image = QImage(
        int(scene_rect.width()) + 1, int(scene_rect.height()) + 1, QImage.Format.Format_RGB32
    )
    image.fill(0)
    painter = QPainter(image)
    win.scene.render(painter, QRectF(image.rect()), scene_rect)
    painter.end()
    center = item.mapToScene(rect.center()) - scene_rect.topLeft()
    pixel = image.pixelColor(int(center.x()), int(center.y()))
    assert (pixel.red(), pixel.green(), pixel.blue()) == (0, 255, 0)


def test_links_still_reach_sockets_after_preview_changes_height(win):
    a = win.controller.add_node("image.grayscale", (0, 0))
    b = win.controller.add_node("image.flip", (300, 0))
    win.controller.connect(a, "image", b, "image")
    link = next(iter(win.graph.links.values()))
    path = win.scene.link_items[link.id].path()
    before = (path.pointAtPercent(0), path.pointAtPercent(1))
    win.scene.node_items[a].set_preview(np.zeros((100, 200, 3), np.uint8))
    win.scene.node_items[b].set_preview(np.zeros((100, 200, 3), np.uint8))
    path = win.scene.link_items[link.id].path()
    assert (path.pointAtPercent(0), path.pointAtPercent(1)) == before


# -- integración con la ventana ----------------------------------------------------------


def build_chain(win, image_path):
    ctl = win.controller
    load_id = ctl.add_node("input.load_image", (-300, 0))
    gray = ctl.add_node("image.grayscale", (0, 0))
    view = ctl.add_node("output.image_viewer", (300, 0))
    number = ctl.add_node("input.number", (0, 300))
    ctl.set_param(load_id, "path", image_path)
    ctl.connect(load_id, "image", gray, "image")
    ctl.connect(gray, "image", view, "image")
    return load_id, gray, view, number


def test_run_shows_previews_only_on_nodes_with_images(qtbot, win, image_path):
    load_id, gray, view, number = build_chain(win, image_path)
    with qtbot.waitSignal(win.runner.finished, timeout=5000):
        win.action_run.trigger()
    items = win.scene.node_items
    assert all(items[i].has_preview for i in (load_id, gray, view))
    assert not items[number].has_preview


def test_preview_toggle_clears_and_restores(qtbot, win, image_path):
    load_id, gray, view, number = build_chain(win, image_path)
    with qtbot.waitSignal(win.runner.finished, timeout=5000):
        win.action_run.trigger()
    win.action_previews.setChecked(False)
    assert not any(i.has_preview for i in win.scene.node_items.values())
    with qtbot.waitSignal(win.runner.finished, timeout=5000):
        win.action_run.trigger()
    assert win.last_result.previews is None  # desactivadas: ni se calculan
    assert not any(i.has_preview for i in win.scene.node_items.values())
    with qtbot.waitSignal(win.runner.finished, timeout=5000):
        win.action_previews.setChecked(True)  # reactivar recalcula
    assert win.scene.node_items[load_id].has_preview


def test_preview_clears_when_a_node_starts_failing(qtbot, win, image_path):
    load_id, gray, view, _ = build_chain(win, image_path)
    with qtbot.waitSignal(win.runner.finished, timeout=5000):
        win.action_run.trigger()
    win.controller.set_param(load_id, "path", "no_existe.png")
    with qtbot.waitSignal(win.runner.finished, timeout=5000):
        win.action_run.trigger()
    assert not any(win.scene.node_items[i].has_preview for i in (load_id, gray, view))


def test_previews_update_in_realtime_and_follow_the_toggle(qtbot, win, tmp_path):
    video = tmp_path / "v.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (64, 48))
    for i in range(10):
        writer.write(np.full((48, 64, 3), 20 * i, np.uint8))
    writer.release()
    ctl = win.controller
    load_id = ctl.add_node("input.load_video", (0, 0))
    view = ctl.add_node("output.video_viewer", (300, 0))
    ctl.set_param(load_id, "path", str(video))
    ctl.set_param(load_id, "loop", True)
    ctl.connect(load_id, "image", view, "image")

    win.action_run.trigger()
    items = win.scene.node_items
    qtbot.waitUntil(lambda: items[view].has_preview, timeout=5000)
    win.action_previews.setChecked(False)
    qtbot.waitUntil(lambda: not items[view].has_preview, timeout=5000)
    qtbot.wait(300)
    assert not items[view].has_preview  # los fotogramas siguientes ya no la devuelven
    win.action_previews.setChecked(True)
    qtbot.waitUntil(lambda: items[view].has_preview, timeout=5000)
    win.runner.stop_realtime(wait=True)


def test_previews_setting_roundtrip(win, tmp_path, monkeypatch, image_path):
    from PySide6.QtWidgets import QFileDialog

    build_chain(win, image_path)
    win.action_previews.setChecked(False)
    path = tmp_path / "p.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    assert win.save_project()
    win.action_previews.setChecked(True)
    assert win.load_project(path)
    assert not win.action_previews.isChecked() and not win.runner.preview_enabled


def test_previews_setting_in_project_data(registry):
    g = Graph(registry)
    _, project = load(dump(g, ProjectData(previews=False), ""), registry)
    assert project.previews is False
    doc = dump(g, ProjectData(), "")
    del doc["settings"]["previews"]  # proyectos anteriores: activadas por defecto
    assert load(doc, registry)[1].previews is True
    doc["settings"]["previews"] = "sí"
    assert load(doc, registry)[1].previews is True


def test_clicking_a_field_still_works_in_a_node_with_preview(win):
    node = win.controller.add_node("image.threshold", (0, 0))
    item = win.scene.node_items[node]
    item.set_preview(np.zeros((100, 200, 3), np.uint8))
    center = item.field_scene_rect("otsu").center()
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    view = win.view
    local = QPointF(view.mapFromScene(center))
    glob = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    mods = Qt.KeyboardModifier.NoModifier
    for kind, button, buttons in (
        (QEvent.Type.MouseButtonPress, left, left),
        (QEvent.Type.MouseButtonRelease, left, none),
    ):
        QApplication.sendEvent(
            view.viewport(), QMouseEvent(kind, local, glob, button, buttons, mods)
        )
    assert win.graph.node(node).params["otsu"] is True
