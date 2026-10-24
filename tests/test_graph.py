import pytest

from palantir_nodes.core.errors import (
    ConnectionRejectedError,
    CycleError,
    GraphError,
    UnknownNodeTypeError,
)
from palantir_nodes.core.graph import GraphEventKind, Link
from palantir_nodes.core.topology import downstream_nodes, topological_order, upstream_nodes
from palantir_nodes.core.validation import Endpoint, check_endpoints


def test_add_node_applies_defaults(graph):
    node = graph.add_node("test.filter", (10, 20))
    assert node.params == {"size": 3, "mode": "a"}
    assert node.input_values == {"amount": 0.5}
    assert node.position == (10.0, 20.0)


def test_unknown_type_raises(graph):
    with pytest.raises(UnknownNodeTypeError):
        graph.add_node("nope")


def test_set_param_coerces_and_emits(graph):
    node = graph.add_node("test.filter")
    events = []
    graph.subscribe(events.append)
    graph.set_param(node.id, "size", 50)
    assert node.params["size"] == 9
    assert [e.kind for e in events] == [GraphEventKind.PARAM_CHANGED]
    graph.set_param(node.id, "size", 9)  # sin cambio: sin evento
    assert len(events) == 1


def test_connect_output_to_input(graph):
    a = graph.add_node("test.source")
    b = graph.add_node("test.filter")
    link = graph.add_link(a.id, "image", b.id, "image")
    assert graph.link_to_input(b.id, "image") == link
    assert graph.connected_inputs(b.id) == {"image"}


def test_reject_two_inputs_and_two_outputs(graph):
    a = graph.add_node("test.filter")
    b = graph.add_node("test.filter")
    check, _, _ = check_endpoints(
        graph, Endpoint(a.id, "image", False), Endpoint(b.id, "image", False)
    )
    assert not check and "dos entradas" in check.reason
    check, _, _ = check_endpoints(
        graph, Endpoint(a.id, "image", True), Endpoint(b.id, "image", True)
    )
    assert not check and "dos salidas" in check.reason


def test_endpoints_normalize_direction(graph):
    a = graph.add_node("test.source")
    b = graph.add_node("test.filter")
    check, src, dst = check_endpoints(
        graph, Endpoint(b.id, "image", False), Endpoint(a.id, "image", True)
    )
    assert check and src.node_id == a.id and dst.node_id == b.id


def test_reject_incompatible_types(graph):
    s = graph.add_node("test.string")
    f = graph.add_node("test.filter")
    check = graph.can_connect(s.id, "text", f.id, "amount")
    assert not check and "incompatibles" in check.reason
    with pytest.raises(ConnectionRejectedError):
        graph.add_link(s.id, "text", f.id, "amount")


def test_implicit_conversion_is_reported(graph):
    src = graph.add_node("test.source")
    f = graph.add_node("test.filter")
    check = graph.can_connect(src.id, "count", f.id, "amount")
    assert check and check.conversion == "Integer → Float"


def test_any_input_accepts_image(graph):
    src = graph.add_node("test.source")
    sink = graph.add_node("test.any_sink")
    assert graph.can_connect(src.id, "image", sink.id, "value")


def test_reject_self_connection(graph):
    f = graph.add_node("test.filter")
    assert not graph.can_connect(f.id, "image", f.id, "image")


def test_reject_cycles(graph):
    a = graph.add_node("test.filter")
    b = graph.add_node("test.filter")
    c = graph.add_node("test.filter")
    graph.add_link(a.id, "image", b.id, "image")
    graph.add_link(b.id, "image", c.id, "image")
    check = graph.can_connect(c.id, "image", a.id, "image")
    assert not check and "ciclo" in check.reason


def test_input_accepts_single_link(graph):
    a = graph.add_node("test.source")
    b = graph.add_node("test.source")
    f = graph.add_node("test.filter")
    graph.add_link(a.id, "image", f.id, "image")
    # Para la UI es válido (reemplaza), pero add_link exige la entrada libre.
    assert graph.can_connect(b.id, "image", f.id, "image")
    with pytest.raises(ConnectionRejectedError):
        graph.add_link(b.id, "image", f.id, "image")


def test_output_accepts_multiple_links(graph):
    a = graph.add_node("test.source")
    f1 = graph.add_node("test.filter")
    f2 = graph.add_node("test.filter")
    graph.add_link(a.id, "image", f1.id, "image")
    graph.add_link(a.id, "image", f2.id, "image")
    assert len(graph.links_from_output(a.id, "image")) == 2


def test_duplicate_link_rejected(graph):
    a = graph.add_node("test.source")
    f = graph.add_node("test.filter")
    graph.add_link(a.id, "image", f.id, "image")
    check = graph.can_connect(a.id, "image", f.id, "image")
    assert not check and "ya existe" in check.reason


def test_remove_node_removes_its_links(graph):
    a = graph.add_node("test.source")
    f = graph.add_node("test.filter")
    graph.add_link(a.id, "image", f.id, "image")
    _, removed = graph.remove_node(a.id)
    assert len(removed) == 1
    assert not graph.links
    with pytest.raises(GraphError):
        graph.node(a.id)


def test_topological_order_and_dependencies(graph):
    f2 = graph.add_node("test.filter")
    f1 = graph.add_node("test.filter")
    src = graph.add_node("test.source")
    graph.add_link(src.id, "image", f1.id, "image")
    graph.add_link(f1.id, "image", f2.id, "image")
    order = topological_order(graph)
    assert order.index(src.id) < order.index(f1.id) < order.index(f2.id)
    assert downstream_nodes(graph, src.id) == {f1.id, f2.id}
    assert upstream_nodes(graph, f2.id) == {src.id, f1.id}


def test_topological_order_detects_cycle(graph):
    a = graph.add_node("test.filter")
    b = graph.add_node("test.filter")
    graph.add_link(a.id, "image", b.id, "image")
    # Se fuerza un ciclo saltándose la validación para comprobar el detector.
    graph._links["x"] = Link("x", b.id, "image", a.id, "image")
    with pytest.raises(CycleError):
        topological_order(graph)
