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


@pytest.fixture
def video_path(tmp_path):
    """Video MJPG de 10 fotogramas (64x48, 25 FPS) con un cuadrado que se mueve."""
    import cv2
    import numpy as np

    path = tmp_path / "vídeo ñ.avi"  # ruta con caracteres no ASCII
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (64, 48))
    assert writer.isOpened()
    for i in range(10):
        frame = np.full((48, 64, 3), 40, np.uint8)
        cv2.rectangle(frame, (4 + i * 4, 10), (20 + i * 4, 30), (200, 120, 60), -1)
        writer.write(frame)
    writer.release()
    return str(path)


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path_factory, monkeypatch):
    """Ninguna prueba lee ni escribe las preferencias reales del usuario."""
    monkeypatch.setenv("PALANTIR_NODES_CONFIG_DIR", str(tmp_path_factory.mktemp("config")))
