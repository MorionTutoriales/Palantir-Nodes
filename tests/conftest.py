import os

# Las pruebas de interfaz no abren ventanas visibles.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from palantir_nodes.core.graph import Graph  # noqa: E402
from palantir_nodes.core.types import SocketType as T  # noqa: E402
from palantir_nodes.nodes.base import NodeDefinition  # noqa: E402
from palantir_nodes.nodes.registry import NodeRegistry  # noqa: E402
from palantir_nodes.nodes.specs import InputSpec, OutputSpec, ParamKind, ParamSpec  # noqa: E402


class Source(NodeDefinition):
    type_id = "test.source"
    label = "Source"
    category = "Test"
    outputs = (OutputSpec("image", T.IMAGE), OutputSpec("count", T.INTEGER))


class Filter(NodeDefinition):
    type_id = "test.filter"
    label = "Filter"
    category = "Test"
    inputs = (InputSpec("image", T.IMAGE), InputSpec("amount", T.FLOAT, default=0.5))
    outputs = (OutputSpec("image", T.IMAGE),)
    params = (
        ParamSpec("size", ParamKind.INT, 3, minimum=1, maximum=9),
        ParamSpec("mode", ParamKind.ENUM, "a", options=(("a", "A"), ("b", "B"))),
    )


class FloatOut(NodeDefinition):
    type_id = "test.float"
    label = "Float"
    category = "Test"
    outputs = (OutputSpec("value", T.FLOAT),)


class StringOut(NodeDefinition):
    type_id = "test.string"
    label = "String"
    category = "Test"
    outputs = (OutputSpec("text", T.STRING),)


class AnySink(NodeDefinition):
    type_id = "test.any_sink"
    label = "Any Sink"
    category = "Test"
    inputs = (InputSpec("value", T.ANY),)


@pytest.fixture
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    for cls in (Source, Filter, FloatOut, StringOut, AnySink):
        reg.register(cls)
    return reg


@pytest.fixture
def graph(registry) -> Graph:
    return Graph(registry)
