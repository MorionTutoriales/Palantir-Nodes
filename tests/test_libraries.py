"""Librerías por proyecto: gestor, nodos de red (WebSocket), exportación, proyectos y ventana."""

import json
import socket
import subprocess
import sys
import time

import cv2
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from palantir_nodes.codegen import CodeGenerator
from palantir_nodes.core.graph import Graph
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.engine.realtime import RealtimeSession
from palantir_nodes.libraries import Requirement, available_libraries, get_library
from palantir_nodes.libraries.manager import LibraryManager
from palantir_nodes.libraries.network.runtime import WebSocketLink
from palantir_nodes.nodes.categories import get_category
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.persistence import ProjectData, dump, embedded_libraries, load
from palantir_nodes.ui.libraries_dialog import LibrariesDialog, library_html
from palantir_nodes.ui.main_window import MainWindow

SERVER, CLIENT = "net.ws_server", "net.ws_client"


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
    """Conexiones abiertas por la prueba: se cierran al terminar aunque falle."""
    opened = []
    yield opened
    for link in opened:
        link.stop()


def open_link(links, mode, address, policy="latest"):
    link = WebSocketLink(mode, address, policy).start()
    links.append(link)
    return link


# -- gestor ---------------------------------------------------------------------------------------


def test_libraries_are_not_registered_until_activated(registry, manager):
    assert SERVER not in registry and CLIENT not in registry and not manager.enabled
    assert [lib.id for lib in available_libraries()] == ["network", "tcp", "mediapipe"]


def test_enable_registers_the_nodes_and_disable_removes_them(registry, manager):
    base = len(registry)
    library = manager.enable("network")
    assert library.id == "network" and manager.is_enabled("network")
    assert SERVER in registry and CLIENT in registry and len(registry) == base + 2
    assert manager.enable("network") is library and len(registry) == base + 2  # idempotente
    manager.disable("network")
    assert SERVER not in registry and len(registry) == base and not manager.enabled
    manager.disable("network")  # desactivar dos veces no falla
    with pytest.raises(KeyError):
        manager.enable("no_existe")


def test_set_enabled_syncs_exactly_and_reports_unknown_ids(registry, manager):
    assert manager.set_enabled(["network", "fantasma"]) == ["fantasma"]
    assert manager.enabled == ["network"] and SERVER in registry
    assert manager.set_enabled([]) == []
    assert not manager.enabled and SERVER not in registry


def test_each_manager_only_touches_its_own_registry(manager):
    other_registry = load_builtin_nodes().copy()
    manager.enable("network")
    assert SERVER not in other_registry and SERVER not in load_builtin_nodes()


def test_library_nodes_appear_in_search_menus_and_the_network_category(registry, manager):
    manager.enable("network")
    assert [c.label for c in registry.search("websocket")] == [
        "WebSocket Client",
        "WebSocket Server",
    ]
    assert "Red" in registry.by_category() and get_category("Red").color
    assert manager.library_of(SERVER).id == "network" and manager.library_of("math.add") is None
    assert manager.type_ids("network") == [SERVER, CLIENT]
    assert manager.type_ids("nada") == []


def test_requirements_report_what_is_missing(monkeypatch):
    library = get_library("network")
    assert [r.package for r in library.requirements] == ["websockets"]
    assert library.install_command == "pip install websockets"
    assert Requirement("modulo_que_no_existe_xyz", "xyz").installed is False
    monkeypatch.setattr(Requirement, "installed", property(lambda self: False))
    assert library.missing == list(library.requirements)
    monkeypatch.setattr(Requirement, "installed", property(lambda self: True))
    assert library.missing == []


# -- WebSocketLink (servidor y cliente reales en localhost) -------------------------------------------


def test_server_and_client_exchange_text_both_ways(links):
    port = free_port()
    server = open_link(links, "server", ("127.0.0.1", port))
    client = open_link(links, "client", f"ws://127.0.0.1:{port}")
    wait_for(lambda: server.read()[0] == 1 and client.read()[0] == 1)
    assert server.read()[1:] == ("", False, "")  # nada recibido todavía

    client.send("hola servidor")
    count, message, new, sender = wait_for(lambda: (r := server.read())[2] and r)
    assert (count, message, new) == (1, "hola servidor", True)
    assert sender.startswith("127.0.0.1:")
    assert server.read()[1:3] == ("hola servidor", False)  # conserva el último, ya no es nuevo

    server.send("hola cliente")
    assert wait_for(lambda: (r := client.read())[2] and r)[1] == "hola cliente"


def test_latest_policy_keeps_only_the_last_and_queue_delivers_in_order(links):
    port_a, port_b = free_port(), free_port()
    latest = open_link(links, "server", ("127.0.0.1", port_a), "latest")
    queued = open_link(links, "server", ("127.0.0.1", port_b), "queue")
    senders = [
        open_link(links, "client", f"ws://127.0.0.1:{port_a}"),
        open_link(links, "client", f"ws://127.0.0.1:{port_b}"),
    ]
    wait_for(lambda: latest.read()[0] == 1 and queued.read()[0] == 1)
    for sender in senders:
        for text in ("uno", "dos", "tres"):
            sender.send(text)
    wait_for(lambda: len(queued._inbox) == 3 and len(latest._inbox) == 3)
    assert latest.read()[1:3] == ("tres", True)
    assert latest.read()[2] is False  # los anteriores se descartaron
    assert [queued.read()[1] for _ in range(3)] == ["uno", "dos", "tres"]
    assert queued.read()[2] is False


def test_binary_messages_are_decoded_and_sending_without_clients_is_harmless(links):
    port = free_port()
    server = open_link(links, "server", ("127.0.0.1", port))
    server.send("nadie escucha")  # sin clientes: no hace nada
    import websockets.sync.client as sync_client

    with sync_client.connect(f"ws://127.0.0.1:{port}") as raw:
        raw.send("héllo ñ".encode())
        assert wait_for(lambda: (r := server.read())[2] and r)[1] == "héllo ñ"


def test_client_keeps_retrying_until_the_server_appears(links):
    port = free_port()
    client = open_link(links, "client", f"ws://127.0.0.1:{port}")
    time.sleep(0.2)
    assert client.read()[0] == 0  # nadie escucha todavía: no es un error
    server = open_link(links, "server", ("127.0.0.1", port))
    wait_for(lambda: client.read()[0] == 1, timeout=6.0)
    assert server.read()[0] == 1


def test_busy_port_reports_a_clear_error(links):
    port = free_port()
    open_link(links, "server", ("127.0.0.1", port))
    with pytest.raises(ValueError, match=f"No se pudo abrir 127.0.0.1:{port}"):
        WebSocketLink("server", ("127.0.0.1", port)).start()


def test_stop_is_idempotent_and_frees_the_port(links):
    port = free_port()
    link = WebSocketLink("server", ("127.0.0.1", port)).start()
    link.stop()
    link.stop()
    link.release()
    again = open_link(links, "server", ("127.0.0.1", port))  # el puerto quedó libre
    assert again.read()[0] == 0


def test_missing_websockets_package_explains_how_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "websockets", None)  # import websockets -> ImportError
    with pytest.raises(ValueError, match="pip install -U websockets"):
        WebSocketLink("server", ("127.0.0.1", free_port())).start()


# -- nodos en el motor ---------------------------------------------------------------------------------


@pytest.fixture
def net_graph(registry, manager):
    manager.enable("network")
    return Graph(registry)


def test_node_declarations(registry, manager):
    manager.enable("network")
    server, client = registry.require(SERVER), registry.require(CLIENT)
    assert server.is_source and client.is_source and not server.cacheable
    assert [o.name for o in server.outputs] == ["clients", "message", "new_message", "sender"]
    assert [o.name for o in client.outputs] == ["connected", "message", "new_message"]
    assert [(i.name, i.optional) for i in server.inputs] == [("send", False), ("message", True)]
    assert server.input("send").default is True
    assert server.default_params() == {"host": "127.0.0.1", "port": 8765, "policy": "latest"}
    assert client.default_params()["url"] == "ws://127.0.0.1:8765"


def test_static_run_does_not_open_connections_or_fail(net_graph):
    server = net_graph.add_node(SERVER, params={"port": free_port()})
    client = net_graph.add_node(CLIENT)
    result = Executor().run(ExecutionPlan.from_graph(net_graph), ExecContext())
    assert result.ok
    assert result.outputs[server.id] == {
        "clients": 0,
        "message": "",
        "new_message": False,
        "sender": "",
    }
    assert result.outputs[client.id] == {"connected": False, "message": "", "new_message": False}


def step_until(session, condition, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = session.step()
        assert result is not None
        if condition(result):
            return result
        time.sleep(0.01)
    raise AssertionError("la condición no se cumplió a tiempo")


def test_server_and_client_nodes_talk_in_a_realtime_session(net_graph):
    port = free_port()
    server = net_graph.add_node(SERVER, params={"port": port})
    client = net_graph.add_node(CLIENT, params={"url": f"ws://127.0.0.1:{port}"})
    session = RealtimeSession(ExecutionPlan.from_graph(net_graph))
    try:
        assert not session._errors
        result = step_until(
            session,
            lambda r: r.outputs[server.id]["clients"] == 1 and r.outputs[client.id]["connected"],
        )
        assert result.ok
        session.ctx.sources[client.id].send("de cliente")
        got = step_until(session, lambda r: r.outputs[server.id]["new_message"])
        assert got.outputs[server.id]["message"] == "de cliente"
        assert got.outputs[server.id]["sender"].startswith("127.0.0.1:")
        session.ctx.sources[server.id].send("de servidor")
        got = step_until(session, lambda r: r.outputs[client.id]["new_message"])
        assert got.outputs[client.id]["message"] == "de servidor"
    finally:
        session.close()


def test_send_is_skipped_without_side_effects_or_when_disabled(net_graph):
    port = free_port()
    server = net_graph.add_node(SERVER, params={"port": port})
    session = RealtimeSession(ExecutionPlan.from_graph(net_graph), side_effects=False)
    sent = []
    try:
        session.step()
        session.ctx.sources[server.id].send = sent.append  # espía
        node = net_graph.node(server.id)
        definition = node.definition
        ctx = session.ctx
        ctx.node_id = server.id
        state = (1, "", False, "")
        ctx.frames = {server.id: state}
        inputs = {"send": True, "message": "hola"}
        definition().process(ctx, inputs, node.params)
        assert sent == []  # side_effects=False: no se envía
        ctx.side_effects = True
        definition().process(ctx, {"send": False, "message": "hola"}, node.params)
        definition().process(ctx, {"send": True, "message": None}, node.params)
        definition().process(ctx, {"send": True, "message": ""}, node.params)
        assert sent == []
        definition().process(ctx, inputs, node.params)
        assert sent == ["hola"]
    finally:
        session.close()


def test_a_busy_port_shows_the_reason_on_the_node(net_graph, links):
    port = free_port()
    open_link(links, "server", ("127.0.0.1", port))
    server = net_graph.add_node(SERVER, params={"port": port})
    session = RealtimeSession(ExecutionPlan.from_graph(net_graph))
    try:
        assert f"No se pudo abrir 127.0.0.1:{port}" in session._errors[server.id][1]
        result = session.step()
        assert result is None or server.id in result.errors
    finally:
        session.close()


# -- exportación ---------------------------------------------------------------------------------------


@pytest.fixture
def image_path(tmp_path):
    img = np.random.default_rng(4).integers(0, 255, (16, 20), dtype=np.uint8)
    path = tmp_path / "in.png"
    cv2.imencode(".png", img)[1].tofile(str(path))
    return str(path)


def export_graph(net_graph, image_path, tmp_path, node_type, params):
    node = net_graph.add_node(node_type, params=params)
    load_node = net_graph.add_node(
        "input.load_image", params={"path": image_path, "mode": "grayscale"}
    )
    thr = net_graph.add_node("image.threshold")
    out = tmp_path / "o.png"
    save = net_graph.add_node("output.save_image", params={"path": str(out)})
    net_graph.add_link(load_node.id, "image", thr.id, "image")
    net_graph.add_link(thr.id, "image", save.id, "image")
    return node, thr, out


def test_exported_script_imports_and_requires_what_the_nodes_need(net_graph, image_path, tmp_path):
    node, thr, out = export_graph(
        net_graph, image_path, tmp_path, SERVER, {"port": free_port(), "host": "127.0.0.1"}
    )
    net_graph.add_link(node.id, "clients", thr.id, "thresh")  # Integer -> parámetro Float
    code = CodeGenerator(ExecutionPlan.from_graph(net_graph), "t").generate()
    assert "pip install opencv-python numpy websockets" in code
    for expected in ("import asyncio", "import threading", "import time", "class WebSocketLink"):
        assert expected in code
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show", "--max-frames", "3"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.exists()


def test_exported_client_script_runs_without_a_server(net_graph, image_path, tmp_path):
    node, thr, out = export_graph(
        net_graph, image_path, tmp_path, CLIENT, {"url": f"ws://127.0.0.1:{free_port()}"}
    )
    net_graph.add_link(node.id, "connected", thr.id, "thresh")  # Boolean -> Float
    code = CodeGenerator(ExecutionPlan.from_graph(net_graph), "t").generate()
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show", "--max-frames", "3"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr


def test_export_blocks_invalid_addresses(net_graph, image_path, tmp_path):
    node, thr, _ = export_graph(net_graph, image_path, tmp_path, CLIENT, {"url": "http://no-es-ws"})
    net_graph.add_link(node.id, "connected", thr.id, "thresh")
    with pytest.raises(Exception, match="ws://"):
        CodeGenerator(ExecutionPlan.from_graph(net_graph), "t").generate()


def test_script_error_when_the_port_is_busy_names_the_node(net_graph, image_path, tmp_path, links):
    port = free_port()
    open_link(links, "server", ("127.0.0.1", port))
    node, thr, _ = export_graph(net_graph, image_path, tmp_path, SERVER, {"port": port})
    net_graph.add_link(node.id, "clients", thr.id, "thresh")
    code = CodeGenerator(ExecutionPlan.from_graph(net_graph), "t").generate()
    script = tmp_path / "s.py"
    script.write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--no-show", "--max-frames", "2"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        proc.returncode != 0
        and "WebSocket Server" in proc.stderr
        and "No se pudo abrir" in proc.stderr
    )


# -- proyecto -----------------------------------------------------------------------------------------


def test_project_file_stores_the_active_libraries(registry, manager):
    manager.enable("network")
    g = Graph(registry)
    g.add_node(SERVER, params={"port": 9000})
    project = ProjectData(libraries=manager.enabled)
    doc = json.loads(json.dumps(dump(g, project, "t")))
    assert doc["libraries"] == ["network"]
    assert embedded_libraries(doc) == (["network"], [])
    graph2, loaded = load(doc, registry)
    assert next(iter(graph2.nodes.values())).params["port"] == 9000
    assert loaded.libraries == []  # la ventana decide cuáles activar, ``load`` no toca el gestor


def test_libraries_field_edge_cases():
    assert embedded_libraries({}) == ([], [])
    assert embedded_libraries({"libraries": "network"})[1]
    ids, warnings = embedded_libraries({"libraries": ["network", "network", 5, "", None, "otra"]})
    assert ids == ["network", "otra"] and len(warnings) == 3
    assert embedded_libraries("no es un dict") == ([], [])


def test_project_without_libraries_field_still_loads(registry):
    doc = dump(Graph(registry), ProjectData(), "t")
    del doc["libraries"]
    assert load(doc, registry)[1].libraries == []


def test_nodes_of_an_inactive_library_are_preserved_not_lost(registry, manager):
    manager.enable("network")
    g = Graph(registry)
    g.add_node(SERVER)
    doc = dump(g, ProjectData(libraries=["network"]), "t")
    manager.set_enabled([])
    graph2, project = load(doc, registry)
    assert not graph2.nodes and project.preserved_nodes[0]["type_id"] == SERVER


# -- diálogo ------------------------------------------------------------------------------------------


def test_dialog_lists_libraries_with_their_state(qtbot):
    dialog = LibrariesDialog(["network"], usage={"network": 3})
    qtbot.addWidget(dialog)
    assert dialog.listing.count() == 3 and dialog.selected_ids() == ["network"]
    html = dialog.details.toPlainText()
    assert "WebSocket Server" in html and "websockets" in html
    assert dialog.warning.text() == ""
    dialog.listing.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected_ids() == [] and "3 nodo(s)" in dialog.warning.text()
    dialog.listing.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.warning.text() == ""


def test_dialog_shows_the_install_command_when_a_package_is_missing(monkeypatch):
    monkeypatch.setattr(Requirement, "installed", property(lambda self: False))
    html = library_html(get_library("network"))
    assert "falta instalarlo" in html and "pip install websockets" in html
    monkeypatch.setattr(Requirement, "installed", property(lambda self: True))
    html = library_html(get_library("network"))
    assert "instalado" in html and "pip install" not in html


# -- ventana -------------------------------------------------------------------------------------------


def make_window(qtbot):
    window = MainWindow(load_builtin_nodes().copy())
    window._confirm_discard = lambda: True
    window.runner.auto_run = False
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


@pytest.fixture
def win(qtbot):
    return make_window(qtbot)


def answer(monkeypatch, button):
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda parent, title, text, *a, **k: asked.append(text) or button),
    )
    return asked


def silence_warnings(monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda p, t, text, *a, **k: shown.append(text))
    )
    return shown


def test_menu_entry_opens_the_dialog_and_applies_the_selection(win, monkeypatch):
    assert win.action_libraries.shortcut().toString() == "Ctrl+Shift+L"

    def fake_exec(self):
        self.listing.item(0).setCheckState(Qt.CheckState.Checked)
        return LibrariesDialog.DialogCode.Accepted

    monkeypatch.setattr(LibrariesDialog, "exec", fake_exec)
    win.action_libraries.trigger()
    assert win.libraries.enabled == ["network"] and SERVER in win.registry
    assert win.project.libraries == ["network"] and not win.undo_stack.isClean()
    assert [c.label for c in win.registry.search("websocket")]


def test_cancelling_the_dialog_changes_nothing(win, monkeypatch):
    monkeypatch.setattr(LibrariesDialog, "exec", lambda self: LibrariesDialog.DialogCode.Rejected)
    win.action_libraries.trigger()
    assert not win.libraries.enabled and SERVER not in win.registry


def test_apply_without_changes_returns_false(win):
    assert win.apply_libraries([]) is False
    assert win.apply_libraries(["network"]) is True
    assert win.apply_libraries(["network"]) is False


def test_disabling_a_library_in_use_asks_and_removes_its_nodes(win, monkeypatch):
    win.apply_libraries(["network"])
    keep = win.controller.add_node("input.number", (0, 0))
    win.controller.add_node(SERVER, (100, 0))
    win.controller.add_node(CLIENT, (100, 100))
    asked = answer(monkeypatch, QMessageBox.StandardButton.No)
    assert win.apply_libraries([]) is False  # el usuario cancela
    assert len(win.graph.nodes) == 3 and win.libraries.enabled == ["network"]
    assert "2 nodo(s)" in asked[0] and "Red (WebSocket)" in asked[0]
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    assert win.apply_libraries([]) is True
    assert set(win.graph.nodes) == {keep} and SERVER not in win.registry
    assert not win.undo_stack.canUndo()


def test_disabling_an_unused_library_needs_no_confirmation(win, monkeypatch):
    win.apply_libraries(["network"])
    asked = answer(monkeypatch, QMessageBox.StandardButton.No)
    assert win.apply_libraries([]) is True and not asked and not win.libraries.enabled


def test_new_project_starts_without_libraries(win):
    win.apply_libraries(["network"])
    win.new_project()
    assert not win.libraries.enabled and SERVER not in win.registry
    assert win.project.libraries == []


def test_saving_and_reopening_restores_the_libraries_and_their_nodes(win, qtbot, tmp_path):
    win.apply_libraries(["network"])
    node = win.controller.add_node(SERVER, (0, 0))
    win.controller.set_param(node, "port", 9123)
    path = tmp_path / "p.json"
    assert win._write_project(path)
    assert json.loads(path.read_text(encoding="utf-8"))["libraries"] == ["network"]

    other = make_window(qtbot)
    assert not other.libraries.enabled
    assert other.load_project(path)
    assert other.libraries.enabled == ["network"] and other.project.libraries == ["network"]
    assert other.graph.node(node).params["port"] == 9123  # el nodo existe, no quedó sin tipo
    assert not other.project.preserved_nodes


def test_opening_a_project_without_libraries_deactivates_the_current_ones(win, tmp_path):
    plain = tmp_path / "plain.json"
    other_window_doc = dump(Graph(win.registry), ProjectData(), "t")
    plain.write_text(json.dumps(other_window_doc), encoding="utf-8")
    win.apply_libraries(["network"])
    assert win.load_project(plain)
    assert not win.libraries.enabled and SERVER not in win.registry


def test_unknown_library_in_a_project_is_reported_and_its_nodes_kept(win, tmp_path, monkeypatch):
    win.apply_libraries(["network"])
    node = win.controller.add_node(SERVER, (0, 0))
    path = tmp_path / "p.json"
    win._write_project(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["libraries"] = ["fantasma"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    shown = silence_warnings(monkeypatch)
    assert win.load_project(path)
    assert not win.libraries.enabled and node not in win.graph.nodes
    assert "fantasma" in shown[0] and win.project.preserved_nodes[0]["type_id"] == SERVER


def test_a_failed_open_restores_the_previous_libraries(win, tmp_path, monkeypatch):
    win.apply_libraries(["network"])
    bad = tmp_path / "malo.json"
    bad.write_text("{ no es json", encoding="utf-8")
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    assert win.load_project(bad) is False
    assert win.libraries.enabled == ["network"] and SERVER in win.registry


def test_opening_a_project_warns_when_a_package_is_missing(win, tmp_path, monkeypatch):
    win.apply_libraries(["network"])
    path = tmp_path / "p.json"
    win._write_project(path)
    monkeypatch.setattr(Requirement, "installed", property(lambda self: False))
    shown = silence_warnings(monkeypatch)
    assert win.load_project(path)
    assert "pip install websockets" in shown[0] and "Red (WebSocket)" in shown[0]


def test_realtime_network_graph_runs_from_the_window(win, qtbot):
    win.apply_libraries(["network"])
    port = free_port()
    server = win.controller.add_node(SERVER, (0, 0))
    win.controller.set_param(server, "port", port)
    viewer = win.controller.add_node("output.image_viewer", (300, 0))
    assert viewer
    assert win.runner.start_realtime(side_effects=True)  # el servidor es una fuente
    qtbot.waitUntil(lambda: win.runner.realtime_active, timeout=5000)
    qtbot.waitUntil(lambda: win.last_result is not None, timeout=5000)
    with socket.create_connection(("127.0.0.1", port), timeout=3):
        pass  # el servidor del nodo está escuchando de verdad
    win.runner.stop_realtime(wait=True)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)  # al detener se cierra


# -- instalar paquetes desde el diálogo ---------------------------------------------------------------------


@pytest.fixture
def installer(monkeypatch, tmp_path):
    """Un «pip» falso: un script de Python; el paquete cuenta como instalado si existe la marca."""
    from palantir_nodes.ui import libraries_dialog

    marker = tmp_path / "instalado.txt"
    state = {"code": 0, "program": sys.executable}
    monkeypatch.setattr(Requirement, "installed", property(lambda self: marker.exists()))

    state["calls"] = []

    def fake_pip(packages, no_deps=False):
        state["calls"].append((no_deps, list(packages)))
        script = (
            f"import sys, pathlib; print('instalando', {packages!r}); "
            f"pathlib.Path({str(marker)!r}).write_text('x') if {state['code']} == 0 else None; "
            f"sys.exit({state['code']})"
        )
        return state["program"], ["-c", script]

    monkeypatch.setattr(libraries_dialog, "pip_command", fake_pip)
    return state, marker


def make_dialog(qtbot):
    dialog = LibrariesDialog([])
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_real_pip_command_targets_the_running_python():
    from palantir_nodes.ui.libraries_dialog import pip_command

    program, args = pip_command(["websockets"])
    assert program == sys.executable and args == ["-m", "pip", "install", "websockets"]


def test_install_button_is_only_shown_when_something_is_missing(qtbot, monkeypatch):
    monkeypatch.setattr(Requirement, "installed", property(lambda self: True))
    dialog = make_dialog(qtbot)
    assert not dialog.install_button.isVisible()
    monkeypatch.setattr(Requirement, "installed", property(lambda self: False))
    dialog.listing.setCurrentRow(1)
    dialog.listing.setCurrentRow(0)
    assert dialog.install_button.isVisible() and dialog.install_button.isEnabled()
    dialog.listing.setCurrentRow(1)  # TCP no necesita paquetes
    assert not dialog.install_button.isVisible()


def test_declining_the_confirmation_installs_nothing(qtbot, installer, monkeypatch):
    dialog = make_dialog(qtbot)
    asked = answer(monkeypatch, QMessageBox.StandardButton.No)
    assert dialog.install_missing() is False
    assert dialog._process is None and not dialog.log.isVisible()
    assert "websockets" in asked[0] and sys.executable in asked[0] or "-c" in asked[0]


def test_successful_install_shows_progress_and_refreshes_the_status(qtbot, installer, monkeypatch):
    state, marker = installer
    dialog = make_dialog(qtbot)
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    assert dialog.install_missing() is True
    assert dialog.log.isVisible() and not dialog.buttons.isEnabled()  # no se puede cerrar ahora
    assert not dialog.install_button.isEnabled() and not dialog.listing.isEnabled()
    dialog.reject()  # a mitad de una instalación no se cierra
    assert dialog.isVisible()
    qtbot.waitUntil(lambda: dialog._process is None, timeout=15000)
    text = dialog.log.toPlainText()
    assert "instalando ['websockets']" in text and "Instalación terminada" in text
    assert marker.exists() and dialog.buttons.isEnabled() and dialog.listing.isEnabled()
    assert not dialog.install_button.isVisible()  # ya no falta nada
    assert "instalado" in dialog.details.toPlainText()


def test_failed_install_reports_the_exit_code_and_keeps_the_button(qtbot, installer, monkeypatch):
    state, marker = installer
    state["code"] = 3
    dialog = make_dialog(qtbot)
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog.install_missing()
    qtbot.waitUntil(lambda: dialog._process is None, timeout=15000)
    assert "no terminó bien (código 3)" in dialog.log.toPlainText() and not marker.exists()
    assert dialog.install_button.isVisible() and dialog.install_button.isEnabled()
    assert dialog.buttons.isEnabled()


def test_install_that_cannot_start_python_is_reported(qtbot, installer, monkeypatch, tmp_path):
    state, _ = installer
    state["program"] = str(tmp_path / "no_existe.exe")
    dialog = make_dialog(qtbot)
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog.install_missing()
    qtbot.waitUntil(lambda: dialog._process is None, timeout=15000)
    assert "No se pudo ejecutar Python" in dialog.log.toPlainText() and dialog.buttons.isEnabled()


def test_packaged_apps_cannot_install(qtbot, installer, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    dialog = make_dialog(qtbot)
    assert dialog.install_missing() is False
    assert dialog.install_button.isVisible() and not dialog.install_button.isEnabled()


def test_nothing_to_install_when_the_library_is_complete(qtbot, monkeypatch):
    monkeypatch.setattr(Requirement, "installed", property(lambda self: True))
    dialog = make_dialog(qtbot)
    assert dialog.install_missing() is False


def test_import_errors_tell_which_python_to_install_into(monkeypatch):
    from palantir_nodes.libraries.mediapipe_lib import runtime as mp

    monkeypatch.setitem(sys.modules, "websockets", None)
    monkeypatch.setitem(sys.modules, "websockets.asyncio", None)
    monkeypatch.setitem(sys.modules, "websockets.asyncio.client", None)
    with pytest.raises(ValueError) as exc:
        WebSocketLink("server", ("127.0.0.1", free_port())).start()
    assert sys.executable in str(exc.value) and "halted" in str(exc.value)  # causa original
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks", None)
    with pytest.raises(ValueError) as exc:
        mp.mp_create("hands", (), "x.task")
    assert sys.executable in str(exc.value) and "pip install mediapipe" in str(exc.value)
