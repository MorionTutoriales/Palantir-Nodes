import pytest
from PySide6.QtGui import QUndoStack

from palantir_nodes.ui.editor.controller import EditorController

pytestmark = pytest.mark.usefixtures("qapp")


def make(graph):
    stack = QUndoStack()
    return EditorController(graph, stack), stack


def test_add_node_undo_redo(graph):
    ctl, stack = make(graph)
    node_id = ctl.add_node("test.filter", (5, 5))
    assert node_id in graph.nodes
    stack.undo()
    assert node_id not in graph.nodes
    stack.redo()
    assert graph.node(node_id).position == (5.0, 5.0)


def test_remove_nodes_restores_links(graph):
    ctl, stack = make(graph)
    a = ctl.add_node("test.source", (0, 0))
    b = ctl.add_node("test.filter", (200, 0))
    assert ctl.connect(a, "image", b, "image")
    ctl.remove_items([a], [])
    assert not graph.links and a not in graph.nodes
    stack.undo()
    assert a in graph.nodes
    assert graph.link_to_input(b, "image") is not None


def test_connect_replaces_and_undo_restores(graph):
    ctl, stack = make(graph)
    a = ctl.add_node("test.source", (0, 0))
    b = ctl.add_node("test.source", (0, 100))
    f = ctl.add_node("test.filter", (200, 0))
    ctl.connect(a, "image", f, "image")
    ctl.connect(b, "image", f, "image")
    assert graph.link_to_input(f, "image").src_node == b
    assert len(graph.links) == 1
    stack.undo()
    assert graph.link_to_input(f, "image").src_node == a
    stack.redo()
    assert graph.link_to_input(f, "image").src_node == b


def test_invalid_connect_pushes_nothing(graph):
    ctl, stack = make(graph)
    s = ctl.add_node("test.string", (0, 0))
    f = ctl.add_node("test.filter", (0, 0))
    count = stack.count()
    assert not ctl.connect(s, "text", f, "amount")
    assert stack.count() == count


def test_move_nodes_undo(graph):
    ctl, stack = make(graph)
    n = ctl.add_node("test.filter", (0, 0))
    ctl.move_nodes({n: ((0.0, 0.0), (50.0, 60.0))})
    assert graph.node(n).position == (50.0, 60.0)
    stack.undo()
    assert graph.node(n).position == (0.0, 0.0)


def test_consecutive_value_changes_merge(graph):
    ctl, stack = make(graph)
    n = ctl.add_node("test.filter", (0, 0))
    base = stack.count()
    for v in (4, 5, 6):
        ctl.set_param(n, "size", v)
    assert stack.count() == base + 1
    assert graph.node(n).params["size"] == 6
    stack.undo()
    assert graph.node(n).params["size"] == 3


def test_input_value_change_undo(graph):
    ctl, stack = make(graph)
    n = ctl.add_node("test.filter", (0, 0))
    ctl.set_input_value(n, "amount", 0.9)
    assert graph.node(n).input_values["amount"] == 0.9
    stack.undo()
    assert graph.node(n).input_values["amount"] == 0.5


def test_invalid_value_is_reported_not_applied(graph):
    ctl, stack = make(graph)
    n = ctl.add_node("test.filter", (0, 0))
    messages = []
    ctl.status_message.connect(messages.append)
    ctl.set_param(n, "mode", "zzz")
    assert graph.node(n).params["mode"] == "a"
    assert messages


def test_insert_payload_remaps_ids_and_links(graph):
    ctl, stack = make(graph)
    a = ctl.add_node("test.source", (0, 0))
    f = ctl.add_node("test.filter", (200, 0))
    ctl.connect(a, "image", f, "image")
    ctl.set_param(f, "size", 7)
    payload = ctl.serialize_nodes([a, f])
    new_ids = ctl.insert_payload(payload, None, "Duplicar")
    assert len(new_ids) == 2 and not set(new_ids) & {a, f}
    assert len(graph.links) == 2
    copy_filter = next(i for i in new_ids if graph.node(i).type_id == "test.filter")
    assert graph.node(copy_filter).params["size"] == 7
    assert graph.node(copy_filter).position == (240.0, 40.0)
    stack.undo()
    assert len(graph.nodes) == 2 and len(graph.links) == 1


def test_insert_payload_skips_unknown_and_invalid(graph):
    ctl, _ = make(graph)
    payload = {
        "nodes": [
            {"id": "x", "type_id": "missing", "position": [0, 0]},
            {"id": "y", "type_id": "test.filter", "position": [0, 0], "params": {"mode": "bad"}},
        ],
        "links": [
            {
                "id": "l",
                "src_node": "y",
                "src_socket": "nope",
                "dst_node": "y",
                "dst_socket": "image",
            }
        ],
    }
    ids = ctl.insert_payload(payload, None, "Pegar")
    assert len(ids) == 1
    assert graph.node(ids[0]).params["mode"] == "a"
    assert not graph.links
