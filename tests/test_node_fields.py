"""Edición de valores dentro del nodo: texto, arrastre, menús y diálogos."""

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.nodes.specs import ParamKind, ParamSpec
from palantir_nodes.ui.editor.field_values import (
    format_field_text,
    parse_field_text,
    scrub_value,
)
from palantir_nodes.ui.main_window import MainWindow

FLOAT = ParamSpec("f", ParamKind.FLOAT, 0.0, minimum=0.0, maximum=255.0, decimals=2)
FLOAT_FREE = ParamSpec("f", ParamKind.FLOAT, 0.0, decimals=3)
INT = ParamSpec("i", ParamKind.INT, 5, minimum=1, maximum=99)
INT_WIDE = ParamSpec("i", ParamKind.INT, 5, minimum=0, maximum=10000)
VEC3 = ParamSpec("v", ParamKind.VECTOR3, (0.0, 0.0, 0.0))
VEC2 = ParamSpec("v", ParamKind.VECTOR2, (0.0, 0.0))
TEXT = ParamSpec("s", ParamKind.STRING, "")


# -- funciones puras ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec,text,expected",
    [
        (INT, "7", 7),
        (INT, " 7.6 ", 8),
        (INT, "-3", -3),
        (FLOAT, "2.5", 2.5),
        (FLOAT, "2,5", 2.5),  # coma decimal
        (FLOAT, "1e2", 100.0),
        (TEXT, "  hola  ", "  hola  "),  # el texto no se recorta
        (VEC3, "1, 2, 3.5", (1.0, 2.0, 3.5)),
        (VEC3, "1 2 3", (1.0, 2.0, 3.0)),
        (VEC3, "1;2;3", (1.0, 2.0, 3.0)),
        (VEC2, "0.5,-1", (0.5, -1.0)),
    ],
)
def test_parse_field_text(spec, text, expected):
    assert parse_field_text(spec, text) == expected


@pytest.mark.parametrize(
    "spec,text,message",
    [
        (INT, "", "Escribe un número"),
        (INT, "abc", "no es un número"),
        (FLOAT, "nan", "finito"),
        (FLOAT, "inf", "finito"),
        (VEC3, "1, 2", "3 valores"),
        (VEC2, "1, 2, 3", "2 valores"),
        (VEC3, "1, x, 3", "no es un número"),
        (ParamSpec("e", ParamKind.ENUM, "a", options=(("a", "A"),)), "a", "no se edita"),
    ],
)
def test_parse_field_text_errors(spec, text, message):
    with pytest.raises(ValueError, match=message):
        parse_field_text(spec, text)


def test_format_field_text_roundtrips():
    assert format_field_text(INT, 7) == "7"
    assert format_field_text(FLOAT, 0.1 + 0.2) == "0.3"
    assert format_field_text(FLOAT, 100.0) == "100"
    assert format_field_text(VEC3, (1.0, 2.5, 3.0)) == "1, 2.5, 3"
    assert format_field_text(TEXT, "x") == "x"
    for spec, value in ((INT, 42), (FLOAT, 12.5), (VEC3, (1.0, 2.5, 3.0))):
        assert parse_field_text(spec, format_field_text(spec, value)) == value


def test_scrub_value_scales_with_range_and_fine_mode():
    assert scrub_value(FLOAT, 100.0, 40) == pytest.approx(100 + 40 * 255 / 400, abs=0.01)
    assert scrub_value(FLOAT, 100.0, 40, fine=True) == pytest.approx(100 + 4 * 255 / 400, abs=0.01)
    assert scrub_value(FLOAT, 100.0, -40) < 100.0
    assert scrub_value(FLOAT_FREE, 0.0, 100) == pytest.approx(1.0)  # 0,01 por píxel
    assert scrub_value(FLOAT_FREE, 50.0, 10) == pytest.approx(55.0)  # 1 % del valor por píxel
    assert scrub_value(INT, 5, 60) == 20  # rango 1-99: 98/400 unidades por píxel
    assert scrub_value(ParamSpec("i", ParamKind.INT, 0), 5, 60) == 15  # sin rango: 1 cada 6 px
    assert scrub_value(INT_WIDE, 0, 40) == 1000  # 10000/400 = 25 unidades por píxel
    assert isinstance(scrub_value(INT, 5, 7), int)


def test_scrub_float_is_rounded_to_decimals():
    value = scrub_value(FLOAT, 0.0, 1)
    assert value == round(value, 2)


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


def send(win, kind, scene_pos, button, buttons, mods=Qt.KeyboardModifier.NoModifier):
    view = win.view
    local = QPointF(view.mapFromScene(scene_pos))
    glob = QPointF(view.viewport().mapToGlobal(local.toPoint()))
    QApplication.sendEvent(view.viewport(), QMouseEvent(kind, local, glob, button, buttons, mods))


def click(win, point):
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    send(win, QEvent.Type.MouseButtonPress, point, left, left)
    send(win, QEvent.Type.MouseButtonRelease, point, left, none)


def drag(win, start, dx, dy=0.0, mods=Qt.KeyboardModifier.NoModifier):
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    end = start + QPointF(dx, dy)
    send(win, QEvent.Type.MouseButtonPress, start, left, left, mods)
    send(win, QEvent.Type.MouseMove, start + QPointF(dx / 2, dy / 2), none, left, mods)
    send(win, QEvent.Type.MouseMove, end, none, left, mods)
    send(win, QEvent.Type.MouseButtonRelease, end, left, none, mods)


def field_center(win, node_id, name, target="param"):
    rect = win.scene.node_items[node_id].field_scene_rect(name, target)
    assert rect is not None, f"{name} no es editable"
    return rect.center()


def make(win, type_id, pos=(0, 0), **params):
    node_id = win.controller.add_node(type_id, pos)
    for name, value in params.items():
        win.controller.set_param(node_id, name, value)
    win.undo_stack.clear()
    return node_id


def param(win, node_id, name):
    return win.graph.node(node_id).params[name]


# hit-testing


def test_field_hit_testing(win):
    add = make(win, "math.add")
    other = win.controller.add_node("input.number", (-300, 0))
    win.controller.connect(other, "value", add, "a")
    item = win.scene.node_items[add]
    assert item.field_scene_rect("a", "input") is None  # conectada: no editable
    assert item.field_scene_rect("b", "input") is not None
    assert item.field_scene_rect("result", "param") is None  # una salida no es campo
    assert item.field_at(QPointF(50, 5)) is None  # encabezado
    row = item.field_at(item.mapFromScene(field_center(win, add, "b", "input")))
    assert row.name == "b" and row.kind == "input"


# booleanos


def test_click_toggles_boolean_and_undo_restores(win):
    node = make(win, "image.threshold")
    assert param(win, node, "otsu") is False
    click(win, field_center(win, node, "otsu"))
    assert param(win, node, "otsu") is True
    assert win.undo_stack.count() == 1
    win.undo_stack.undo()
    assert param(win, node, "otsu") is False


# texto en línea


def open_editor(win, node, name, target="param"):
    click(win, field_center(win, node, name, target))
    editor = win.view.field_editor.inline
    assert editor is not None and editor.isVisible()
    return editor


def test_click_number_opens_inline_editor_and_enter_commits(qtbot, win):
    node = make(win, "image.gaussian_blur", ksize=5)
    editor = open_editor(win, node, "ksize")
    assert editor.text() == "5" and editor.selectedText() == "5"
    assert editor.parent() is win  # no es hijo de la vista (atajos de una letra)
    editor.setText("21")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert param(win, node, "ksize") == 21 and win.view.field_editor.inline is None
    win.undo_stack.undo()
    assert param(win, node, "ksize") == 5


def test_inline_editor_is_placed_over_the_field(win):
    node = make(win, "image.gaussian_blur")
    editor = open_editor(win, node, "sigma")
    view = win.view
    rect = view.mapFromScene(win.scene.node_items[node].field_scene_rect("sigma")).boundingRect()
    expected = view.viewport().mapTo(win, rect.topLeft())
    assert editor.geometry().topLeft() == expected
    assert editor.height() >= 22


def test_escape_cancels_without_changes(qtbot, win):
    node = make(win, "image.gaussian_blur", ksize=5)
    editor = open_editor(win, node, "ksize")
    editor.setText("33")
    qtbot.keyClick(editor, Qt.Key.Key_Escape)
    assert param(win, node, "ksize") == 5 and win.undo_stack.count() == 0
    assert win.view.field_editor.inline is None


def test_invalid_text_reports_and_keeps_value(qtbot, win):
    node = make(win, "image.gaussian_blur", ksize=5)
    messages = []
    win.controller.status_message.connect(messages.append)
    editor = open_editor(win, node, "ksize")
    editor.setText("muchos")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert param(win, node, "ksize") == 5 and win.undo_stack.count() == 0
    assert messages and "no es un número" in messages[0]


def test_out_of_range_value_is_clamped(qtbot, win):
    node = make(win, "image.gaussian_blur", ksize=5)
    editor = open_editor(win, node, "ksize")
    editor.setText("999")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert param(win, node, "ksize") == 99


def test_losing_focus_or_closing_commits(win):
    node = make(win, "image.gaussian_blur", ksize=5)
    editor = open_editor(win, node, "ksize")
    editor.setText("9")
    win.view.field_editor.close_inline(commit=True)  # lo que ocurre al hacer zoom/panning
    assert param(win, node, "ksize") == 9
    editor = open_editor(win, node, "ksize")
    editor.setText("11")
    editor.clearFocus()
    editor.commit()
    assert param(win, node, "ksize") == 11


def test_opening_another_field_commits_the_previous_one(win):
    node = make(win, "image.gaussian_blur", ksize=5, sigma=0.0)
    editor = open_editor(win, node, "ksize")
    editor.setText("15")
    open_editor(win, node, "sigma")
    assert param(win, node, "ksize") == 15


def test_vector_field_is_edited_as_text(qtbot, win):
    node = make(win, "image.in_range")
    editor = open_editor(win, node, "lower")
    assert editor.text() == "0, 0, 0"
    editor.setText("10, 20.5, 30")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert param(win, node, "lower") == (10.0, 20.5, 30.0)


def test_unconnected_input_default_is_editable(qtbot, win):
    add = make(win, "math.add")
    editor = open_editor(win, add, "b", "input")
    editor.setText("2,5")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert win.graph.node(add).input_values["b"] == 2.5
    win.undo_stack.undo()
    assert win.graph.node(add).input_values["b"] == 0.0


def test_typing_in_the_editor_does_not_trigger_editor_shortcuts(qtbot, win):
    node = make(win, "image.gaussian_blur")
    other = make(win, "image.canny", (400, 0))
    win.scene.select_nodes([node, other])
    editor = open_editor(win, node, "ksize")
    qtbot.keyClicks(editor, "xaX")
    qtbot.keyClick(editor, Qt.Key.Key_Delete)
    qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    assert node in win.graph.nodes and other in win.graph.nodes
    editor.cancel()


# arrastre


def test_dragging_a_number_scrubs_in_a_single_undo_step(win):
    node = make(win, "image.threshold", thresh=100.0)
    start = field_center(win, node, "thresh")
    position = win.graph.node(node).position
    drag(win, start, 80)
    value = param(win, node, "thresh")
    assert value == pytest.approx(100 + 80 * 255 / 400, abs=2.0)
    assert win.undo_stack.count() == 1  # un solo paso
    assert win.graph.node(node).position == position  # no movió el nodo
    assert win.view.field_editor.inline is None  # arrastrar no abre el editor
    win.undo_stack.undo()
    assert param(win, node, "thresh") == 100.0


def test_scrub_is_clamped_to_the_range_and_works_leftwards(win):
    node = make(win, "image.threshold", thresh=100.0)
    drag(win, field_center(win, node, "thresh"), 5000)
    assert param(win, node, "thresh") == 255.0
    drag(win, field_center(win, node, "thresh"), -5000)
    assert param(win, node, "thresh") == 0.0


def test_scrub_integer_and_fine_mode(win):
    node = make(win, "image.gaussian_blur", ksize=5)
    drag(win, field_center(win, node, "ksize"), 60)
    assert param(win, node, "ksize") == 20
    coarse = make(win, "image.threshold", (400, 0), thresh=100.0)
    fine = make(win, "image.threshold", (400, 300), thresh=100.0)
    drag(win, field_center(win, coarse, "thresh"), 100)
    drag(win, field_center(win, fine, "thresh"), 100, mods=Qt.KeyboardModifier.ControlModifier)
    assert abs(param(win, fine, "thresh") - 100) < abs(param(win, coarse, "thresh") - 100) / 5


def test_small_movement_is_still_a_click(win):
    node = make(win, "image.gaussian_blur", ksize=5)
    drag(win, field_center(win, node, "ksize"), 2)  # por debajo del umbral
    assert win.view.field_editor.inline is not None
    win.view.field_editor.close_inline(commit=False)
    assert param(win, node, "ksize") == 5


def test_dragging_from_a_non_numeric_field_does_nothing(win, monkeypatch):
    node = make(win, "image.threshold", method="binary")
    calls = []
    monkeypatch.setattr(win.view.field_editor, "_choose_enum", lambda *a: calls.append(1))
    position = win.graph.node(node).position
    drag(win, field_center(win, node, "method"), 60, 20)
    assert not calls and win.graph.node(node).position == position
    assert win.undo_stack.count() == 0


def test_dragging_the_header_still_moves_the_node(win):
    node = make(win, "image.threshold", (0, 0))
    header = win.scene.node_items[node].scenePos() + QPointF(60, 10)
    drag(win, header, 100, 50)
    assert win.graph.node(node).position == pytest.approx((100, 50), abs=2)


def test_clicking_a_field_selects_only_that_node(win):
    a = make(win, "image.threshold", (0, 0))
    b = make(win, "image.canny", (400, 0))
    win.scene.select_nodes([a, b])
    click(win, field_center(win, a, "otsu"))
    assert win.scene.selected_node_ids() == [a]


# menús y diálogos


def test_enum_field_uses_menu_choice(win, monkeypatch):
    node = make(win, "image.threshold", method="binary")
    seen = {}

    def choose(spec, current):
        seen["current"], seen["options"] = current, [v for v, _ in spec.options]
        return "trunc"

    monkeypatch.setattr(win.view.field_editor, "_choose_enum", choose)
    click(win, field_center(win, node, "method"))
    assert param(win, node, "method") == "trunc"
    assert seen["current"] == "binary" and "tozero_inv" in seen["options"]
    monkeypatch.setattr(win.view.field_editor, "_choose_enum", lambda *a: None)  # cancelado
    click(win, field_center(win, node, "method"))
    assert param(win, node, "method") == "trunc"
    win.undo_stack.undo()
    assert param(win, node, "method") == "binary"


def test_color_field_uses_color_dialog(win, monkeypatch):
    node = make(win, "input.color")
    monkeypatch.setattr(win.view.field_editor, "_choose_color", lambda current: (1, 2, 3))
    click(win, field_center(win, node, "color"))
    assert param(win, node, "color") == (1, 2, 3)
    monkeypatch.setattr(win.view.field_editor, "_choose_color", lambda current: None)
    click(win, field_center(win, node, "color"))
    assert param(win, node, "color") == (1, 2, 3)


def test_file_field_uses_file_dialog(win, monkeypatch):
    node = make(win, "input.load_image")
    seen = []
    monkeypatch.setattr(
        win.view.field_editor, "_choose_file", lambda spec, cur: seen.append(spec) or "C:/a/b.png"
    )
    click(win, field_center(win, node, "path"))
    assert param(win, node, "path") == "C:/a/b.png" and not seen[0].save_dialog
    save = make(win, "output.save_image", (400, 0))
    monkeypatch.setattr(win.view.field_editor, "_choose_file", lambda spec, cur: seen.append(spec))
    click(win, field_center(win, save, "path"))
    assert seen[-1].save_dialog and param(win, save, "path") == ""  # cancelado


def test_properties_panel_follows_in_node_edits(qtbot, win):
    node = make(win, "image.gaussian_blur", ksize=5)
    editor = open_editor(win, node, "ksize")
    editor.setText("31")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert win.properties.node_id == node
    assert win.properties._param_widgets["ksize"].spin.value() == 31


def test_edits_mark_the_project_dirty(qtbot, win):
    node = make(win, "image.threshold")
    win.undo_stack.setClean()
    click(win, field_center(win, node, "otsu"))
    assert not win.undo_stack.isClean()
