"""Tiempo real: sesión sin Qt, liberación de recursos y script exportado con video."""

import os
import subprocess
import sys

import cv2
import numpy as np
import pytest

from palantir_nodes.codegen import CodeGenerator, ExportError
from palantir_nodes.core.graph import Graph
from palantir_nodes.engine.executor import ExecContext, Executor
from palantir_nodes.engine.plan import ExecutionPlan
from palantir_nodes.engine.realtime import RealtimeSession, source_nodes
from palantir_nodes.nodes.registry import load_builtin_nodes


@pytest.fixture(scope="module")
def registry():
    return load_builtin_nodes()


@pytest.fixture
def g(registry):
    return Graph(registry)


def plan_of(graph):
    return ExecutionPlan.from_graph(graph)


def run_to_end(session, limit=200):
    results = []
    while len(results) < limit:
        result = session.step()
        if result is None:
            break
        results.append(result)
    return results


def video_chain(g, video_path, *type_ids, loop=False):
    load = g.add_node("input.load_video", params={"path": video_path, "loop": loop})
    prev, ids = load, [load.id]
    for type_id in type_ids:
        node = g.add_node(type_id)
        g.add_link(prev.id, prev.definition.outputs[0].name, node.id, "image")
        prev = node
        ids.append(node.id)
    return ids


def read_video(path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


# -- sesión ------------------------------------------------------------------------------


def test_session_plays_every_frame_then_finishes(g, video_path):
    ids = video_chain(g, video_path, "image.grayscale", "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    try:
        results = run_to_end(session)
        assert len(results) == 10
        assert session.finished and "Load Video" in session.finish_reason
        assert all(r.ok for r in results)
        # Cada fotograma es distinto (el cuadrado se mueve) y gris.
        images = [r.images[ids[2]] for r in results]
        assert images[0].ndim == 2 and images[0].shape == (48, 64)
        assert not np.array_equal(images[0], images[5])
        assert session.step() is None
    finally:
        session.close()


def test_loop_never_ends(g, video_path):
    video_chain(g, video_path, "output.video_viewer", loop=True)
    session = RealtimeSession(plan_of(g))
    try:
        assert len(run_to_end(session, limit=35)) == 35
        assert not session.finished
    finally:
        session.close()


def test_source_recomputes_every_frame_but_unrelated_nodes_stay_cached(g, video_path):
    load, gray, view = video_chain(g, video_path, "image.grayscale", "output.video_viewer")
    number = g.add_node("input.number")
    session = RealtimeSession(plan_of(g))
    try:
        first, second = session.step(), session.step()
        assert {load, gray, view} <= second.computed
        assert number.id in second.cached and number.id in first.computed
    finally:
        session.close()


def test_file_sources_are_paced_at_their_frame_rate(g, video_path):
    video_chain(g, video_path, "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    try:
        assert session.target_interval == pytest.approx(1 / 25)
    finally:
        session.close()


def test_static_mode_shows_first_frame_and_webcam_explains(g, video_path):
    load, view = video_chain(g, video_path, "output.video_viewer")
    cam = g.add_node("input.webcam")
    static = Executor().run(plan_of(g), ExecContext())
    first = read_video(video_path)[0]
    assert np.array_equal(static.outputs[load]["image"], first)
    assert "solo funciona en tiempo real" in static.errors[cam.id]


def test_missing_video_reports_error_and_ends(g):
    load, view = video_chain(g, "no_existe.avi", "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    try:
        result = session.step()
        assert "No existe el archivo" in result.errors[load]
        assert view in result.blocked
        assert session.finished and "No existe" in session.finish_reason
        assert session.step() is None
    finally:
        session.close()


def test_garbage_video_file_reports_error(g, tmp_path):
    bad = tmp_path / "roto.avi"
    bad.write_bytes(b"no soy un video")
    load, _ = video_chain(g, str(bad), "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    try:
        assert "No se pudo abrir el video" in session.step().errors[load]
    finally:
        session.close()


def test_webcam_failure_is_reported_not_raised(g, monkeypatch):
    from palantir_nodes.nodes.library import inputs

    def boom(index):
        raise ValueError(f"No se pudo abrir la cámara {index} (¿está en uso o desconectada?)")

    monkeypatch.setattr(inputs, "open_camera_capture", boom)
    cam = g.add_node("input.webcam", params={"index": 3})
    view = g.add_node("output.video_viewer")
    g.add_link(cam.id, "image", view.id, "image")
    session = RealtimeSession(plan_of(g))
    try:
        assert "cámara 3" in session.step().errors[cam.id]
    finally:
        session.close()


def test_plan_update_applies_param_changes_and_keeps_source(g, video_path):
    load, thr, view = video_chain(g, video_path, "image.threshold", "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    try:
        source_before = session._sources[load][1]
        dark = session.step().images[view]
        g.set_param(thr, "thresh", 0.0)
        session.set_plan(plan_of(g))
        bright = session.step().images[view]
        assert session._sources[load][1] is source_before  # no se reabrió el archivo
        assert int(bright.sum()) > int(dark.sum())
    finally:
        session.close()


def test_plan_update_reopens_source_when_its_params_change(g, video_path, tmp_path):
    load, view = video_chain(g, video_path, "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    try:
        before = session._sources[load][1]
        g.set_param(load, "loop", True)
        session.set_plan(plan_of(g))
        assert session._sources[load][1] is not before
        assert not before.is_open  # la anterior se liberó
    finally:
        session.close()


def test_removed_source_ends_session(g, video_path):
    load, view = video_chain(g, video_path, "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    try:
        session.step()
        g.remove_node(load)
        session.set_plan(plan_of(g))
        assert not source_nodes(plan_of(g))
        session.step()
        assert session.finished and "no tiene fuentes" in session.finish_reason
    finally:
        session.close()


# -- liberación de recursos --------------------------------------------------------------


def test_close_releases_video_file(g, video_path):
    video_chain(g, video_path, "output.video_viewer")
    session = RealtimeSession(plan_of(g))
    capture = session._sources[next(iter(session._sources))][1]
    session.step()
    session.close()
    assert not capture.is_open
    os.remove(video_path)  # en Windows falla si el archivo sigue abierto
    session.close()  # idempotente


def test_close_releases_writer_and_output_is_readable(g, video_path, tmp_path):
    load, view = video_chain(g, video_path, "image.canny")
    out = tmp_path / "salida.avi"
    save = g.add_node("output.save_video", params={"path": str(out), "codec": "MJPG", "fps": 25.0})
    g.add_link(view, "edges", save.id, "image")
    session = RealtimeSession(plan_of(g))
    run_to_end(session)
    assert save.id in session.ctx.resources
    session.close()
    assert not session.ctx.resources
    assert len(read_video(out)) == 10
    os.remove(out)  # el escritor liberó el archivo


def test_save_video_does_nothing_in_static_mode_or_without_side_effects(g, video_path, tmp_path):
    out = tmp_path / "no_debe_existir.avi"
    (load,) = video_chain(g, video_path)
    save = g.add_node("output.save_video", params={"path": str(out), "codec": "MJPG"})
    g.add_link(load, "image", save.id, "image")
    assert Executor().run(plan_of(g), ExecContext()).ok and not out.exists()
    session = RealtimeSession(plan_of(g), side_effects=False)
    run_to_end(session)
    session.close()
    assert not out.exists()


def test_save_video_errors_are_reported(g, video_path, tmp_path):
    (load,) = video_chain(g, video_path)
    save = g.add_node("output.save_video", params={"path": str(tmp_path / "x.avi")})
    g.add_link(load, "image", save.id, "image")
    session = RealtimeSession(plan_of(g))
    try:
        assert session.step().ok
        session.ctx.close_resources()
        g.set_param(save.id, "path", str(tmp_path / "no_hay_carpeta" / "y.avi"))
        session.set_plan(plan_of(g))
        assert "No se pudo crear el video" in session.step().errors[save.id]
    finally:
        session.close()


# -- exportación a script con bucle de video ---------------------------------------------


def generate(graph):
    return CodeGenerator(ExecutionPlan.from_graph(graph), "test").generate()


def run_script(code, tmp_path, *args):
    script = tmp_path / "exportado.py"
    script.write_text(code, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), "--no-show", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def graph_with_save(g, video_path, out):
    load, canny = video_chain(g, video_path, "image.canny")
    blur = g.add_node("image.gaussian_blur", params={"ksize": 5})
    g.add_link(load, "image", blur.id, "image")
    save = g.add_node("output.save_video", params={"path": str(out), "codec": "MJPG", "fps": 25.0})
    g.add_link(canny, "edges", save.id, "image")
    view = g.add_node("output.video_viewer")
    g.add_link(blur.id, "image", view.id, "image")
    return save


def test_video_script_structure(g, video_path, tmp_path):
    graph_with_save(g, video_path, tmp_path / "o.avi")
    code = generate(g)
    compile(code, "script", "exec")
    for fragment in (
        "while True:",
        "finally:",
        ".release()",
        "--max-frames",
        "read_frame(",
        "open_video_capture(",
        "open_video_writer(",
        "cv2.imshow",
        "'q'",
    ):
        assert fragment in code, fragment
    assert "palantir_nodes" not in code and "PySide6" not in code


def test_webcam_script_structure(g):
    cam = g.add_node("input.webcam", params={"index": 2})
    view = g.add_node("output.video_viewer")
    g.add_link(cam.id, "image", view.id, "image")
    code = generate(g)
    compile(code, "script", "exec")
    assert "open_camera_capture(2)" in code and "CAP_DSHOW" in code
    assert code.count(".release()") >= 1


def test_video_script_equals_engine(g, video_path, tmp_path):
    out = tmp_path / "salida.avi"
    graph_with_save(g, video_path, out)
    session = RealtimeSession(plan_of(g))
    run_to_end(session)
    session.close()
    expected = read_video(out)
    assert len(expected) == 10
    out.unlink()

    proc = run_script(generate(g), tmp_path)
    assert proc.returncode == 0, proc.stderr
    got = read_video(out)
    assert len(got) == len(expected)
    assert all(np.array_equal(a, b) for a, b in zip(got, expected, strict=True))


def test_video_script_max_frames_and_loop(g, video_path, tmp_path):
    out = tmp_path / "salida.avi"
    (load,) = video_chain(g, video_path, loop=True)
    save = g.add_node("output.save_video", params={"path": str(out), "codec": "MJPG"})
    g.add_link(load, "image", save.id, "image")
    proc = run_script(generate(g), tmp_path, "--max-frames", "23")
    assert proc.returncode == 0, proc.stderr
    assert len(read_video(out)) == 23  # repite el video hasta alcanzar el límite
    out.unlink()  # el script liberó el archivo


def test_video_script_names_the_failing_node(g, video_path, tmp_path):
    video_chain(g, video_path, "output.video_viewer")
    code = generate(g)
    os.remove(video_path)
    proc = run_script(code, tmp_path)
    assert proc.returncode != 0
    assert "Error en el nodo 'Load Video'" in proc.stderr
    assert "No existe el archivo" in proc.stderr


def test_video_export_problems(g):
    load = g.add_node("input.load_video")
    view = g.add_node("output.video_viewer")
    g.add_link(load.id, "image", view.id, "image")
    with pytest.raises(ExportError, match="ningún archivo de video"):
        generate(g)
    save = g.add_node("output.save_video")
    g.add_link(load.id, "image", save.id, "image")
    g.set_param(load.id, "path", "x.avi")
    with pytest.raises(ExportError, match="destino"):
        generate(g)
    g.set_param(save.id, "path", "sin_extension")
    with pytest.raises(ExportError, match="extensión"):
        generate(g)
