"""Guardado y carga de proyectos: ida y vuelta, validación, migraciones y tolerancia."""

import json

import pytest

from palantir_nodes.core.graph import Graph
from palantir_nodes.nodes.registry import load_builtin_nodes
from palantir_nodes.persistence import (
    CURRENT_VERSION,
    ProjectData,
    ProjectFormatError,
    dump,
    load,
    migrate,
    read_project,
    write_project,
)


@pytest.fixture(scope="module")
def registry():
    return load_builtin_nodes()


@pytest.fixture
def g(registry):
    return Graph(registry)


def sample_graph(g):
    load_node = g.add_node(
        "input.load_image",
        (-300.5, 20.25),
        params={"path": "C:/img/ñandú.png", "mode": "grayscale"},
    )
    blur = g.add_node("image.gaussian_blur", (0, 0), params={"ksize": 9, "sigma": 1.25})
    rng = g.add_node(
        "image.in_range", (200, 50), params={"lower": (1.0, 2.0, 3.0), "upper": (9.0, 8.0, 7.0)}
    )
    g.add_node("image.draw_contours", (400, 0), params={"color": (10, 20, 30)})
    blend = g.add_node("compose.blend", (0, 300), input_values={"factor": 0.25})
    number = g.add_node("input.number", (-300, 300), params={"value": 0.75})
    g.add_link(load_node.id, "image", blur.id, "image")
    g.add_link(blur.id, "image", rng.id, "image")
    g.add_link(load_node.id, "image", blend.id, "image_a")
    g.add_link(rng.id, "mask", blend.id, "image_b")
    g.add_link(number.id, "value", blend.id, "factor")
    return g


def roundtrip(g, registry, project=None):
    project = project or ProjectData()
    text = json.dumps(dump(g, project, "t"))
    return load(json.loads(text), registry)


def snapshot(g):
    return (
        [n.to_dict() for n in g.nodes.values()],
        [link.to_dict() for link in g.links.values()],
    )


# -- ida y vuelta ------------------------------------------------------------------------


def test_roundtrip_preserves_everything(g, registry):
    sample_graph(g)
    graph2, project = roundtrip(g, registry)
    nodes1, links1 = snapshot(g)
    nodes2, links2 = snapshot(graph2)
    assert nodes2 == nodes1 and links2 == links1
    assert not project.warnings
    # los tipos se restauran (tuplas, no listas)
    assert graph2.node(nodes1[2]["id"]).params["lower"] == (1.0, 2.0, 3.0)
    assert graph2.node(nodes1[3]["id"]).params["color"] == (10, 20, 30)


def test_dump_is_idempotent_and_stable(g, registry):
    sample_graph(g)
    first = dump(g, ProjectData(name="demo"), "1.0")
    graph2, project2 = load(json.loads(json.dumps(first)), registry)
    second = dump(graph2, project2, "1.0")
    for doc in (first, second):
        doc["meta"].pop("saved_at")
    assert first == second


def test_header_fields(g):
    sample_graph(g)
    doc = dump(g, ProjectData(name="Mi proyecto"), "9.9")
    assert doc["format"] == "palantir-nodes" and doc["version"] == CURRENT_VERSION
    assert doc["meta"]["name"] == "Mi proyecto" and doc["meta"]["app_version"] == "9.9"
    assert {"nodes", "links", "editor", "settings", "meta"} <= set(doc)


def test_editor_state_and_settings_roundtrip(g, registry):
    project = ProjectData(name="x", auto_run=False, zoom=1.75, center=(120.5, -33.0))
    _, loaded = roundtrip(g, registry, project)
    assert (loaded.name, loaded.auto_run, loaded.zoom, loaded.center) == (
        "x",
        False,
        1.75,
        (120.5, -33.0),
    )


def test_bad_editor_state_falls_back_to_defaults(g, registry):
    doc = dump(g, ProjectData(), "")
    doc["editor"] = {"zoom": -3, "center": ["a", None]}
    doc["settings"] = {"auto_run": "sí"}
    _, project = load(doc, registry)
    assert (project.zoom, project.center, project.auto_run) == (1.0, (0.0, 0.0), True)


def test_empty_project(g, registry):
    graph2, project = roundtrip(g, registry)
    assert not graph2.nodes and not graph2.links and not project.warnings


# -- archivos ----------------------------------------------------------------------------


def test_write_and_read_file_with_unicode_path(g, registry, tmp_path):
    sample_graph(g)
    path = tmp_path / "proyecto ñ.json"
    write_project(path, dump(g, ProjectData(name="ñandú"), "t"))
    assert not list(tmp_path.glob("*.tmp"))
    text = path.read_text(encoding="utf-8")
    assert "ñandú" in text and text.endswith("\n")  # sin escapes \uXXXX
    graph2, _ = load(read_project(path), registry)
    assert snapshot(graph2) == snapshot(g)


def test_write_is_atomic_when_data_is_invalid(g, tmp_path):
    path = tmp_path / "p.json"
    write_project(path, dump(g, ProjectData(name="original"), ""))
    bad = dump(g, ProjectData(), "")
    bad["editor"]["zoom"] = float("nan")
    with pytest.raises(ValueError):
        write_project(path, bad)
    assert json.loads(path.read_text(encoding="utf-8"))["meta"]["name"] == "original"
    assert not list(tmp_path.glob("*.tmp"))


def test_write_failure_keeps_old_file_and_cleans_temp(g, tmp_path, monkeypatch):
    import os

    path = tmp_path / "p.json"
    write_project(path, dump(g, ProjectData(name="original"), ""))

    def boom(*_args):
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disco lleno"):
        write_project(path, dump(g, ProjectData(name="nuevo"), ""))
    monkeypatch.undo()
    assert json.loads(path.read_text(encoding="utf-8"))["meta"]["name"] == "original"
    assert not list(tmp_path.glob("*.tmp"))


def test_write_to_missing_folder_raises_oserror(g, tmp_path):
    with pytest.raises(OSError):
        write_project(tmp_path / "no_hay" / "p.json", dump(g, ProjectData(), ""))


@pytest.mark.parametrize(
    "content,message",
    [
        (b"", "está vacío"),
        (b"   \n", "está vacío"),
        (b"{ esto no es json", "no es JSON válido"),
        (b"\xff\xfe\x00bad", "UTF-8"),
    ],
)
def test_read_rejects_bad_files(tmp_path, content, message):
    path = tmp_path / "malo.json"
    path.write_bytes(content)
    with pytest.raises(ProjectFormatError, match=message):
        read_project(path)


def test_read_missing_file(tmp_path):
    with pytest.raises(ProjectFormatError, match="No se puede abrir"):
        read_project(tmp_path / "no_existe.json")


# -- cabecera y versiones ----------------------------------------------------------------


@pytest.mark.parametrize(
    "data,message",
    [
        ([], "se esperaba un objeto"),
        ("texto", "se esperaba un objeto"),
        ({}, "No es un proyecto"),
        ({"format": "otro", "version": 1}, "No es un proyecto"),
        ({"format": "palantir-nodes"}, "Versión de formato inválida"),
        ({"format": "palantir-nodes", "version": "1"}, "Versión de formato inválida"),
        ({"format": "palantir-nodes", "version": True}, "Versión de formato inválida"),
        ({"format": "palantir-nodes", "version": 0}, "Versión de formato inválida"),
    ],
)
def test_invalid_headers(registry, data, message):
    with pytest.raises(ProjectFormatError, match=message):
        load(data, registry)


def test_newer_version_is_rejected_with_clear_message(registry):
    data = {"format": "palantir-nodes", "version": CURRENT_VERSION + 1, "nodes": [], "links": []}
    with pytest.raises(ProjectFormatError, match="más nuevo"):
        load(data, registry)


def test_migrations_are_applied_in_order():
    def v1_to_v2(d):
        d = dict(d, version=2)
        d["nodes"] = [{**n, "type_id": n["type_id"].replace("old.", "new.")} for n in d["nodes"]]
        return d

    def v2_to_v3(d):
        return dict(d, version=3, migrated=True)

    old = {"format": "palantir-nodes", "version": 1, "nodes": [{"type_id": "old.blur"}]}
    out = migrate(old, current=3, migrations={1: v1_to_v2, 2: v2_to_v3})
    assert out["version"] == 3 and out["migrated"] and out["nodes"][0]["type_id"] == "new.blur"
    assert old["version"] == 1  # el original no se modifica


def test_missing_or_broken_migration_is_an_error():
    data = {"format": "palantir-nodes", "version": 1}
    with pytest.raises(ProjectFormatError, match="No hay migración"):
        migrate(data, current=2, migrations={})
    with pytest.raises(ProjectFormatError, match="no actualizó"):
        migrate(data, current=2, migrations={1: lambda d: d})


def test_structure_errors_are_fatal(registry):
    data = {"format": "palantir-nodes", "version": 1, "nodes": {}, "links": "x"}
    with pytest.raises(ProjectFormatError) as exc:
        load(data, registry)
    assert len(exc.value.problems) == 2


# -- tolerancia: nodos y conexiones individuales -----------------------------------------


def doc_with(g, **extra):
    sample_graph(g)
    doc = dump(g, ProjectData(), "")
    doc.update(extra)
    return doc


def test_unknown_node_types_are_preserved_on_resave(g, registry):
    doc = doc_with(g)
    ghost = {
        "id": "ghost1",
        "type_id": "plugin.magic",
        "position": [5, 5],
        "params": {"power": 11},
        "input_values": {},
    }
    some_known = doc["nodes"][1]["id"]
    doc["nodes"].append(ghost)
    doc["links"].append(
        {
            "id": "gl",
            "src_node": "ghost1",
            "src_socket": "out",
            "dst_node": some_known,
            "dst_socket": "image",
        }
    )
    graph2, project = load(doc, registry)
    assert "ghost1" not in graph2.nodes and len(graph2.nodes) == 6
    assert any("plugin.magic" in w for w in project.warnings)
    assert project.preserved_nodes == [ghost] and project.preserved_links[0]["id"] == "gl"

    saved = dump(graph2, project, "")
    assert ghost in saved["nodes"]
    assert any(link["id"] == "gl" for link in saved["links"])
    # y sobrevive a otra ida y vuelta
    graph3, project3 = load(json.loads(json.dumps(saved)), registry)
    assert project3.preserved_nodes == [ghost]
    assert len(graph3.links) == len(graph2.links)


def test_invalid_nodes_are_skipped_with_warnings(g, registry):
    doc = doc_with(g)
    first_id = doc["nodes"][0]["id"]
    doc["nodes"] += [
        "no soy un objeto",
        {"id": "", "type_id": "image.grayscale"},
        {"type_id": "image.grayscale"},
        {"id": "x", "type_id": 5},
        {"id": first_id, "type_id": "image.grayscale"},  # duplicado
    ]
    graph2, project = load(doc, registry)
    assert len(graph2.nodes) == 6
    assert len(project.warnings) == 5
    assert any("duplicado" in w for w in project.warnings)


def test_bad_params_fall_back_to_defaults_with_warnings(g, registry):
    doc = {
        "format": "palantir-nodes",
        "version": 1,
        "nodes": [
            {
                "id": "a",
                "type_id": "image.gaussian_blur",
                "position": ["x", 1],
                "params": {"ksize": "abc", "sigma": 2.5, "inexistente": 1},
                "input_values": [],
            },
            {
                "id": "b",
                "type_id": "image.threshold",
                "position": [1, 2],
                "params": {"method": "zzz", "thresh": 5000},
            },
            {
                "id": "c",
                "type_id": "math.add",
                "position": [float("inf"), 0],
                "input_values": {"a": "no número", "b": 2, "c": 3},
            },
        ],
        "links": [],
    }
    graph2, project = load(doc, registry)
    a, b, c = (graph2.node(i) for i in "abc")
    assert a.params == {"ksize": 5, "sigma": 2.5} and a.position == (0.0, 0.0)
    assert b.params["method"] == "binary" and b.params["thresh"] == 255.0  # recortado al máximo
    assert c.input_values == {"a": 0.0, "b": 2.0} and c.position == (0.0, 0.0)
    assert len(project.warnings) >= 7


def test_invalid_links_are_skipped_with_reasons(g, registry):
    doc = doc_with(g)
    ids = {n["type_id"]: n["id"] for n in doc["nodes"]}
    load_id, blur_id = ids["input.load_image"], ids["image.gaussian_blur"]
    number = ids["input.number"]
    doc["links"] += [
        "no es objeto",
        {"id": "l1", "src_node": load_id},  # incompleto
        {
            "id": "l2",
            "src_node": "nada",
            "src_socket": "image",
            "dst_node": blur_id,
            "dst_socket": "image",
        },
        {
            "id": "l3",
            "src_node": number,
            "src_socket": "value",
            "dst_node": blur_id,
            "dst_socket": "image",
        },  # tipos incompatibles
        {
            "id": "l4",
            "src_node": load_id,
            "src_socket": "nope",
            "dst_node": blur_id,
            "dst_socket": "image",
        },
        {
            "id": "l5",
            "src_node": load_id,
            "src_socket": "image",
            "dst_node": blur_id,
            "dst_socket": "image",
        },  # la entrada ya está conectada
        {
            "id": doc["links"][0]["id"],
            "src_node": load_id,
            "src_socket": "image",
            "dst_node": blur_id,
            "dst_socket": "image",
        },  # id duplicado
    ]
    graph2, project = load(doc, registry)
    assert len(graph2.links) == 5  # solo las originales
    assert len(project.warnings) == 7


def test_cycles_in_file_are_rejected(g, registry):
    a = g.add_node("image.grayscale")
    b = g.add_node("image.grayscale")
    g.add_link(a.id, "image", b.id, "image")
    doc = dump(g, ProjectData(), "")
    doc["links"].append(
        {
            "id": "back",
            "src_node": b.id,
            "src_socket": "image",
            "dst_node": a.id,
            "dst_socket": "image",
        }
    )
    graph2, project = load(doc, registry)
    assert len(graph2.links) == 1 and any("ciclo" in w for w in project.warnings)


def test_node_without_optional_fields_gets_defaults(registry):
    doc = {
        "format": "palantir-nodes",
        "version": 1,
        "nodes": [{"id": "n", "type_id": "image.canny"}],
    }
    graph2, project = load(doc, registry)
    node = graph2.node("n")
    assert node.params == registry.require("image.canny").default_params()
    assert node.position == (0.0, 0.0) and not project.warnings
