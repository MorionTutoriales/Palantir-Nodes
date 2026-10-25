"""Librerías TCP y MediaPipe (MediaPipe con un paquete falso: no se necesitan modelos ni Internet)."""

import os
import socket
import subprocess
import sys
import textwrap
import time
import types

import cv2
import numpy as np
import pytest

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.graph import Graph
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.engine.realtime import RealtimeSession
from palantir_nodes.libraries import available_libraries, get_library
from palantir_nodes.libraries.manager import LibraryManager
from palantir_nodes.libraries.mediapipe_lib import runtime as mp
from palantir_nodes.libraries.tcp.runtime import TcpLink
from palantir_nodes.nodes.categories import get_category
from palantir_nodes.nodes.registry import load_builtin_nodes

TCP_SERVER, TCP_CLIENT = "net.tcp_server", "net.tcp_client"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(condition, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("tiempo de espera agotado")


@pytest.fixture
def registry():
    return load_builtin_nodes().copy()


@pytest.fixture
def manager(registry):
    return LibraryManager(registry)


@pytest.fixture
def links():
    opened = []
    yield opened
    for link in opened:
        link.stop()


def open_link(links, mode, address, policy="latest"):
    link = TcpLink(mode, address, policy).start()
    links.append(link)
    return link


def run_script(tmp_path, graph, *extra, env=None):
    code = CodeGenerator(ExecutionPlan.from_graph(graph), "t").generate()
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show", *extra],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return code, proc


def read_png(path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)


# -- registro de librerías ------------------------------------------------------------------------


def test_the_three_libraries_are_available_in_order():
    assert [lib.id for lib in available_libraries()] == ["network", "tcp", "mediapipe"]
    assert get_library("tcp").requirements == ()  # solo biblioteca estándar
    assert [r.package for r in get_library("mediapipe").requirements] == ["mediapipe"]
    assert get_library("mediapipe").install_command == "pip install mediapipe"


def test_enabling_all_libraries_registers_every_node_without_clashes(registry, manager):
    manager.set_enabled(["network", "tcp", "mediapipe"])
    expected = {
        "net.ws_server",
        "net.ws_client",
        TCP_SERVER,
        TCP_CLIENT,
        "mp.hands",
        "mp.pose",
        "mp.face_mesh",
        "mp.face_detection",
        "mp.landmark_point",
    }
    assert expected <= {c.type_id for c in registry}
    assert get_category("Red").color and get_category("MediaPipe").color
    manager.set_enabled(["tcp"])
    assert TCP_SERVER in registry and "mp.hands" not in registry and "net.ws_server" not in registry


# -- TcpLink -----------------------------------------------------------------------------------------


def test_tcp_server_and_client_exchange_lines_both_ways(links):
    port = free_port()
    server = open_link(links, "server", ("127.0.0.1", port))
    client = open_link(links, "client", ("127.0.0.1", port))
    wait_for(lambda: server.read()[0] == 1 and client.read()[0] == 1)

    client.send("hola servidor")
    count, message, new, sender = wait_for(lambda: (r := server.read())[2] and r)
    assert (count, message, new) == (1, "hola servidor", True) and sender.startswith("127.0.0.1:")
    server.send("hola cliente")
    assert wait_for(lambda: (r := client.read())[2] and r)[1] == "hola cliente"


def test_tcp_messages_are_lines_partial_lines_wait_and_crlf_is_stripped(links):
    port = free_port()
    server = open_link(links, "server", ("127.0.0.1", port), "queue")
    with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
        raw.sendall(b"uno\r\ndos\ntr")  # la última línea está incompleta
        wait_for(lambda: len(server._inbox) == 2)
        assert [server.read()[1] for _ in range(2)] == ["uno", "dos"]
        assert server.read()[2] is False  # «tr» todavía no es un mensaje
        raw.sendall("es ñ\n".encode())
        assert wait_for(lambda: (r := server.read())[2] and r)[1] == "tres ñ"


def test_tcp_sent_text_never_contains_inner_line_breaks(links):
    port = free_port()
    server = open_link(links, "server", ("127.0.0.1", port))
    with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
        wait_for(lambda: server.read()[0] == 1)
        server.send("a\nb\r\nc")
        raw.settimeout(3)
        data = b""
        while not data.endswith(b"\n"):
            data += raw.recv(100)
    assert data == b"a b  c\n"  # un solo mensaje de una línea


def test_tcp_closed_client_is_forgotten_and_server_keeps_working(links):
    port = free_port()
    server = open_link(links, "server", ("127.0.0.1", port))
    raw = socket.create_connection(("127.0.0.1", port), timeout=3)
    wait_for(lambda: server.read()[0] == 1)
    raw.close()
    wait_for(lambda: server.read()[0] == 0)
    with socket.create_connection(("127.0.0.1", port), timeout=3):
        wait_for(lambda: server.read()[0] == 1)


def test_tcp_client_retries_until_the_server_appears(links):
    port = free_port()
    client = open_link(links, "client", ("127.0.0.1", port))
    time.sleep(0.2)
    assert client.read()[0] == 0
    server = open_link(links, "server", ("127.0.0.1", port))
    wait_for(lambda: client.read()[0] == 1, timeout=6.0)
    assert server.read()[0] == 1


def test_tcp_busy_port_and_repeated_stop(links):
    port = free_port()
    open_link(links, "server", ("127.0.0.1", port))
    with pytest.raises(ValueError, match=f"No se pudo abrir 127.0.0.1:{port}"):
        TcpLink("server", ("127.0.0.1", port)).start()
    other = TcpLink("server", ("127.0.0.1", free_port())).start()
    other.stop()
    other.stop()


# -- nodos TCP ---------------------------------------------------------------------------------------


def test_tcp_nodes_declaration(registry, manager):
    manager.enable("tcp")
    server, client = registry.require(TCP_SERVER), registry.require(TCP_CLIENT)
    assert server.is_source and client.is_source and not server.cacheable
    assert server.default_params() == {"host": "127.0.0.1", "port": 9000, "policy": "latest"}
    assert client.default_params() == {"host": "127.0.0.1", "port": 9000, "policy": "latest"}
    assert [o.name for o in client.outputs] == ["connected", "message", "new_message"]


def test_tcp_nodes_talk_in_a_realtime_session(registry, manager):
    manager.enable("tcp")
    g = Graph(registry)
    port = free_port()
    server = g.add_node(TCP_SERVER, params={"port": port})
    client = g.add_node(TCP_CLIENT, params={"port": port})
    session = RealtimeSession(ExecutionPlan.from_graph(g))
    try:
        assert not session._errors

        def step(condition):
            deadline = time.time() + 6
            while time.time() < deadline:
                result = session.step()
                if condition(result):
                    return result
                time.sleep(0.01)
            raise AssertionError("no se cumplió")

        step(lambda r: r.outputs[server.id]["clients"] == 1 and r.outputs[client.id]["connected"])
        session.ctx.sources[client.id].send("ping")
        got = step(lambda r: r.outputs[server.id]["new_message"])
        assert got.outputs[server.id]["message"] == "ping"
        session.ctx.sources[server.id].send("pong")
        got = step(lambda r: r.outputs[client.id]["new_message"])
        assert got.outputs[client.id]["message"] == "pong"
    finally:
        session.close()


def test_tcp_exported_script_needs_no_extra_package_and_runs(registry, manager, tmp_path):
    manager.enable("tcp")
    g = Graph(registry)
    img = np.random.default_rng(1).integers(0, 255, (10, 12), dtype=np.uint8)
    src = tmp_path / "in.png"
    cv2.imencode(".png", img)[1].tofile(str(src))
    node = g.add_node(TCP_SERVER, params={"port": free_port()})
    load = g.add_node("input.load_image", params={"path": str(src), "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    out = tmp_path / "o.png"
    save = g.add_node("output.save_image", params={"path": str(out)})
    g.add_link(node.id, "clients", thr.id, "thresh")
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", save.id, "image")
    code, proc = run_script(tmp_path, g, "--max-frames", "3")
    assert proc.returncode == 0, proc.stderr
    assert "pip install opencv-python numpy\n" in code and "websockets" not in code
    assert "class LinkBase" in code and "class TcpLink(LinkBase)" in code and out.exists()


def test_script_with_websocket_and_tcp_emits_the_shared_base_once(registry, manager, tmp_path):
    manager.set_enabled(["network", "tcp"])
    g = Graph(registry)
    img = np.zeros((8, 8), np.uint8)
    src = tmp_path / "in.png"
    cv2.imencode(".png", img)[1].tofile(str(src))
    ws = g.add_node("net.ws_server", params={"port": free_port()})
    tcp = g.add_node(TCP_SERVER, params={"port": free_port()})
    both = g.add_node("math.add")
    g.add_link(ws.id, "clients", both.id, "a")
    g.add_link(tcp.id, "clients", both.id, "b")
    load = g.add_node("input.load_image", params={"path": str(src), "mode": "grayscale"})
    thr = g.add_node("image.threshold")
    save = g.add_node("output.save_image", params={"path": str(tmp_path / "o.png")})
    g.add_link(both.id, "result", thr.id, "thresh")
    g.add_link(load.id, "image", thr.id, "image")
    g.add_link(thr.id, "image", save.id, "image")
    code, proc = run_script(tmp_path, g, "--max-frames", "2")
    assert proc.returncode == 0, proc.stderr
    assert (
        code.count("class LinkBase") == 1 and "websockets" in code.splitlines()[4:8][0] + code[:400]
    )


# -- MediaPipe: nodos ---------------------------------------------------------------------------------


def hand(points):
    return {"points": points, "box": (1.0, 2.0, 30.0, 40.0), "score": 1.0}


@pytest.fixture
def mp_registry(registry, manager):
    manager.enable("mediapipe")
    return registry


def test_mediapipe_nodes_declaration(mp_registry):
    hands = mp_registry.require("mp.hands")
    assert [o.name for o in hands.outputs] == ["image", "count", "landmarks", "boxes"]
    assert [p.name for p in hands.params] == ["max", "confidence", "draw", "model"]
    assert hands.default_params() == {"max": 2, "confidence": 0.5, "draw": True, "model": ""}
    assert [p.name for p in mp_registry.require("mp.face_detection").params] == [
        "confidence",
        "draw",
        "model",
    ]
    point = mp_registry.require("mp.landmark_point")
    assert [o.name for o in point.outputs] == ["point", "x", "y", "found"]
    assert mp_registry.require("mp.pose").default_params()["max"] == 1


def test_mediapipe_nodes_can_pin_the_viewer_and_connect_by_type(mp_registry):
    g = Graph(mp_registry)
    hands = g.add_node("mp.hands")
    point = g.add_node("mp.landmark_point")
    load = g.add_node("input.load_image")
    viewer = g.add_node("output.image_viewer")
    g.add_link(load.id, "image", hands.id, "image")
    g.add_link(hands.id, "landmarks", point.id, "landmarks")  # Any -> Any
    g.add_link(hands.id, "image", viewer.id, "image")
    assert len(g.links) == 3


@pytest.mark.parametrize(
    "subject,index,expected",
    [
        (0, 1, (11.0, 12.0, True)),
        (1, 0, (50.0, 60.0, True)),
        (2, 0, (0.0, 0.0, False)),
        (0, 5, (0.0, 0.0, False)),
        (-1, 0, (0.0, 0.0, False)),
    ],
)
def test_pick_landmark(subject, index, expected):
    landmarks = [[(10, 11), (11, 12)], [(50, 60)]]
    assert mp.pick_landmark(landmarks, subject, index) == expected


def test_landmark_point_node_with_and_without_a_connection(mp_registry):
    cls = mp_registry.require("mp.landmark_point")
    out = cls().process(
        ExecContext(),
        {"landmarks": [[(1, 2), (3, 4)]]},
        {"subject": 0, "index": 1},
    )
    assert out == {"point": (3.0, 4.0), "x": 3.0, "y": 4.0, "found": True}
    none = cls().process(ExecContext(), {"landmarks": None}, {"subject": 0, "index": 1})
    assert none["found"] is False and none["point"] == (0.0, 0.0)


@pytest.fixture
def fake_detection(monkeypatch):
    """Sustituye el detector real: crea un objeto falso y devuelve una mano fija."""
    created = []

    class Detector:
        def __init__(self, kind, options):
            self.kind, self.options, self.closed = kind, options, False
            created.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(mp, "mp_model_path", lambda kind, custom="": custom or f"{kind}.task")
    monkeypatch.setattr(mp, "mp_create", lambda kind, options, path: Detector(kind, options))
    points = [(float(i), float(i + 1)) for i in range(21)]
    monkeypatch.setattr(mp, "mp_detect", lambda det, kind, image: [hand(points)])
    return created


def test_hand_node_outputs_and_drawing(mp_registry, fake_detection):
    g = Graph(mp_registry)
    img = np.zeros((60, 80, 3), np.uint8)
    hands = mp_registry.require("mp.hands")
    ctx = ExecContext()
    out = hands().process(
        ctx, {"image": img}, {**hands.default_params(), "max": 3, "confidence": 0.7}
    )
    assert (
        out["count"] == 1
        and len(out["landmarks"][0]) == 21
        and out["boxes"] == [(1.0, 2.0, 30.0, 40.0)]
    )
    assert (
        out["image"].shape == img.shape and out["image"].any() and not img.any()
    )  # dibuja en una copia
    assert fake_detection[0].options == (("max", 3), ("confidence", 0.7))
    plain = hands().process(ctx, {"image": img}, {**hands.default_params(), "draw": False})
    assert plain["image"] is img or np.array_equal(plain["image"], img)
    assert g is not None


def test_detector_is_created_once_recreated_on_changes_and_closed_with_the_context(
    mp_registry, fake_detection
):
    hands = mp_registry.require("mp.hands")
    img = np.zeros((20, 20, 3), np.uint8)
    ctx = ExecContext()
    ctx.node_id = "n1"
    params = hands.default_params()
    for _ in range(3):
        hands().process(ctx, {"image": img}, params)
    assert len(fake_detection) == 1  # un solo detector aunque se procesen varios fotogramas
    hands().process(ctx, {"image": img}, {**params, "confidence": 0.9})
    assert len(fake_detection) == 2 and fake_detection[0].closed and not fake_detection[1].closed
    ctx.node_id = "n2"
    hands().process(ctx, {"image": img}, params)
    assert len(fake_detection) == 3  # cada nodo tiene el suyo
    ctx.close_resources()
    assert all(d.closed for d in fake_detection) and not ctx.resources


def test_gray_images_are_accepted_and_come_back_as_color(mp_registry, fake_detection):
    hands = mp_registry.require("mp.hands")
    gray = np.zeros((30, 40), np.uint8)
    out = hands().process(ExecContext(), {"image": gray}, hands.default_params())
    assert out["image"].shape == (30, 40, 3)


def test_missing_mediapipe_package_explains_how_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks", None)
    with pytest.raises(ValueError, match="pip install mediapipe"):
        mp.mp_create("hands", (), "x.task")


# -- MediaPipe: modelos ----------------------------------------------------------------------------------


def test_custom_model_must_exist(tmp_path):
    model = tmp_path / "mi.task"
    model.write_bytes(b"x")
    assert mp.mp_model_path("hands", str(model)) == str(model)
    with pytest.raises(ValueError, match="No existe el modelo"):
        mp.mp_model_path("hands", str(tmp_path / "otro.task"))


def test_official_model_is_downloaded_once_into_the_models_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("PALANTIR_NODES_MODELS", str(tmp_path / "modelos"))
    calls = []

    def fake_retrieve(url, target):
        calls.append(url)
        with open(target, "wb") as handle:
            handle.write(b"modelo")

    monkeypatch.setattr(mp.urllib.request, "urlretrieve", fake_retrieve)
    path = mp.mp_model_path("hands")
    assert path == str(tmp_path / "modelos" / "hand_landmarker.task")
    assert open(path, "rb").read() == b"modelo" and calls[0].startswith(
        "https://storage.googleapis.com/"
    )
    assert mp.mp_model_path("hands") == path and len(calls) == 1  # ya está: no se vuelve a bajar
    assert not (tmp_path / "modelos" / "hand_landmarker.task.part").exists()


def test_failed_download_explains_where_to_get_the_model_and_leaves_no_partial_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PALANTIR_NODES_MODELS", str(tmp_path / "modelos"))

    def failing(url, target):
        with open(target, "wb") as handle:
            handle.write(b"a medias")
        raise OSError("sin conexión")

    monkeypatch.setattr(mp.urllib.request, "urlretrieve", failing)
    with pytest.raises(ValueError, match=r"sin conexión.*Descárgalo de https://.*«Modelo»"):
        mp.mp_model_path("pose")
    assert not list((tmp_path / "modelos").glob("*"))


def test_models_dir_defaults_to_the_home_folder(monkeypatch):
    monkeypatch.delenv("PALANTIR_NODES_MODELS", raising=False)
    assert mp.mp_models_dir().endswith(os.path.join(".palantir_nodes", "models"))


# -- MediaPipe: conversión de resultados (con un mediapipe falso) -------------------------------------------


@pytest.fixture
def fake_mediapipe_module(monkeypatch):
    module = types.ModuleType("mediapipe")
    module.ImageFormat = types.SimpleNamespace(SRGB=1)
    module.Image = lambda image_format, data: types.SimpleNamespace(data=data)
    monkeypatch.setitem(sys.modules, "mediapipe", module)
    return module


def point(x, y):
    return types.SimpleNamespace(x=x, y=y)


def test_landmark_results_are_converted_to_pixels(fake_mediapipe_module):
    result = types.SimpleNamespace(hand_landmarks=[[point(0.5, 0.25), point(1.0, 1.0)]])
    detector = types.SimpleNamespace(detect=lambda image: result)
    image = np.zeros((40, 80, 3), np.uint8)
    found = mp.mp_detect(detector, "hands", image)
    assert found == [
        {"points": [(40.0, 10.0), (80.0, 40.0)], "box": (40.0, 10.0, 40.0, 30.0), "score": 1.0}
    ]
    empty = types.SimpleNamespace(detect=lambda image: types.SimpleNamespace(pose_landmarks=[]))
    assert mp.mp_detect(empty, "pose", image) == []


def test_face_detection_results_use_the_pixel_box_and_keypoints(fake_mediapipe_module):
    box = types.SimpleNamespace(origin_x=5, origin_y=6, width=20, height=30)
    detection = types.SimpleNamespace(
        bounding_box=box,
        categories=[types.SimpleNamespace(score=0.9)],
        keypoints=[point(0.5, 0.5)],
    )
    detector = types.SimpleNamespace(
        detect=lambda image: types.SimpleNamespace(detections=[detection])
    )
    found = mp.mp_detect(detector, "face_detection", np.zeros((100, 200), np.uint8))  # gris
    assert found == [
        {"points": [(100.0, 50.0)], "box": (5, 6, 20, 30), "score": pytest.approx(0.9)}
    ]


def test_drawing_uses_the_rgb_colour_and_does_not_touch_the_input():
    image = np.zeros((50, 50, 3), np.uint8)
    found = [{"points": [(10.0, 10.0), (30.0, 10.0)], "box": (0, 0, 0, 0), "score": 1}]
    out = mp.mp_draw(image, "hands", found, color=(255, 0, 0))  # rojo en RGB
    assert not image.any() and tuple(out[10, 10]) == (0, 0, 255)  # rojo en BGR
    assert tuple(out[10, 20]) == (0, 0, 255)  # la unión entre los puntos 0 y 1
    boxes = mp.mp_draw(image, "face_detection", [{"points": [], "box": (5, 5, 10, 10), "score": 1}])
    assert boxes[5, 8].any()
    assert mp.mp_draw(np.zeros((4, 4), np.uint8), "pose", []).shape == (4, 4, 3)


# -- MediaPipe: extremo a extremo con un paquete falso en disco ---------------------------------------------

STUB = {
    "mediapipe/__init__.py": """
        class ImageFormat:
            SRGB = 1
        class Image:
            def __init__(self, image_format, data):
                self.data = data
    """,
    "mediapipe/tasks/__init__.py": "",
    "mediapipe/tasks/python/__init__.py": """
        class BaseOptions:
            def __init__(self, model_asset_path):
                self.model_asset_path = model_asset_path
    """,
    "mediapipe/tasks/python/vision.py": """
        class RunningMode:
            IMAGE = 1
        class _Options:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
        class HandLandmarkerOptions(_Options):
            pass
        class _P:
            def __init__(self, x, y):
                self.x, self.y = x, y
        class _Result:
            def __init__(self, hands):
                self.hand_landmarks = hands
        class HandLandmarker:
            @classmethod
            def create_from_options(cls, options):
                return cls()
            def detect(self, image):
                return _Result([[_P(0.2 + 0.03 * i, 0.3 + 0.02 * i) for i in range(21)]])
            def close(self):
                pass
    """,
}


@pytest.fixture
def stub_dir(tmp_path):
    root = tmp_path / "stub"
    for name, content in STUB.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
    models = tmp_path / "modelos"
    models.mkdir()
    (models / "hand_landmarker.task").write_bytes(b"modelo falso")
    return root, models


def test_engine_and_exported_script_give_the_same_result_with_a_stub_mediapipe(
    mp_registry, tmp_path, stub_dir, monkeypatch
):
    root, models = stub_dir
    img = np.random.default_rng(3).integers(0, 255, (60, 80, 3), dtype=np.uint8)
    src = tmp_path / "in.png"
    cv2.imencode(".png", img)[1].tofile(str(src))
    g = Graph(mp_registry)
    load = g.add_node("input.load_image", params={"path": str(src)})
    hands = g.add_node("mp.hands", params={"max": 1, "confidence": 0.6})
    pick = g.add_node("mp.landmark_point", params={"subject": 0, "index": 8})
    thr = g.add_node("image.threshold")
    gray = g.add_node("image.grayscale")
    out_marked, out_thr = tmp_path / "marked.png", tmp_path / "thr.png"
    save_marked = g.add_node("output.save_image", params={"path": str(out_marked)})
    save_thr = g.add_node("output.save_image", params={"path": str(out_thr)})
    g.add_link(load.id, "image", hands.id, "image")
    g.add_link(hands.id, "landmarks", pick.id, "landmarks")
    g.add_link(hands.id, "image", save_marked.id, "image")
    g.add_link(hands.id, "image", gray.id, "image")
    g.add_link(gray.id, "image", thr.id, "image")
    g.add_link(pick.id, "x", thr.id, "thresh")  # el punto detectado alimenta un parámetro
    g.add_link(thr.id, "image", save_thr.id, "image")

    monkeypatch.syspath_prepend(str(root))
    for name in [n for n in sys.modules if n == "mediapipe" or n.startswith("mediapipe.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setenv("PALANTIR_NODES_MODELS", str(models))
    ctx = ExecContext(side_effects=True)
    result = Executor().run(ExecutionPlan.from_graph(g), ctx)
    ctx.close_resources()
    assert result.ok, result.errors
    assert result.outputs[hands.id]["count"] == 1 and result.outputs[pick.id]["found"]
    engine = [read_png(out_marked), read_png(out_thr)]
    assert engine[0].any() and not np.array_equal(engine[0], img)
    out_marked.unlink()
    out_thr.unlink()

    env = {**os.environ, "PYTHONPATH": str(root), "PALANTIR_NODES_MODELS": str(models)}
    code, proc = run_script(tmp_path, g, env=env)
    assert proc.returncode == 0, proc.stderr
    assert "pip install opencv-python numpy mediapipe" in code
    for expected in ("import urllib.request", "_MP_STORE = {}", "def mp_detect", "MP_HAND_LINES"):
        assert expected in code
    for expected_image, path in zip(engine, (out_marked, out_thr), strict=True):
        assert np.array_equal(read_png(path), expected_image)


def test_realtime_script_closes_the_detectors_at_the_end(mp_registry, tmp_path, stub_dir):
    root, models = stub_dir
    g = Graph(mp_registry)
    tick = g.add_node("input.tick", params={"interval": 0.01})
    load = g.add_node("input.load_image", params={"path": "x.png"})
    hands = g.add_node("mp.hands")
    viewer = g.add_node("output.image_viewer")
    g.add_link(load.id, "image", hands.id, "image")
    g.add_link(hands.id, "image", viewer.id, "image")
    text = g.add_node("convert.number_to_string")
    shown = g.add_node("output.string_viewer")
    g.add_link(tick.id, "time", text.id, "value")  # el Tick hace que el script sea de tiempo real
    g.add_link(text.id, "text", shown.id, "text")
    code = CodeGenerator(ExecutionPlan.from_graph(g), "t").generate()
    assert "finally:" in code and "mp_close_all(_MP_STORE)" in code
    compile(code, "script", "exec")
