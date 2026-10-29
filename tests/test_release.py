"""Versión descargable: autocomprobación, construcción, notas de la release y flujos de GitHub."""

import hashlib
import importlib
import re
import sys
import tomllib
from pathlib import Path

import pytest

from palantir_nodes import __version__, app, selftest
from palantir_nodes.ui import theme

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


@pytest.fixture(scope="module")
def build_release():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        yield importlib.import_module("build_release")
    finally:
        sys.path.remove(str(ROOT / "tools"))


@pytest.fixture
def release_notes(build_release):
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        yield importlib.import_module("release_notes")
    finally:
        sys.path.remove(str(ROOT / "tools"))


# -- --version y --selftest -----------------------------------------------------------------------


def test_version_flag_prints_and_exits_without_opening_a_window(capsys):
    assert app.main(["palantir", "--version"]) == 0
    assert capsys.readouterr().out.strip() == f"Palantir Nodes {__version__}"


def test_selftest_passes_and_leaves_the_environment_as_it_was(qapp, monkeypatch, tmp_path, capsys):
    log = tmp_path / "resultado.txt"
    monkeypatch.setenv("PALANTIR_SELFTEST_LOG", str(log))
    monkeypatch.setenv("PALANTIR_NODES_CONFIG_DIR", str(tmp_path / "mi_config"))
    try:
        assert app.main(["palantir", "--selftest"]) == 0
    finally:
        qapp.setStyleSheet("")
        theme.apply_skin("oscuro")
    assert "correcta" in capsys.readouterr().out
    assert "correcta" in log.read_text(encoding="utf-8")
    import os

    assert os.environ["PALANTIR_NODES_CONFIG_DIR"] == str(tmp_path / "mi_config")
    assert not (tmp_path / "mi_config").exists()  # no escribió en la configuración real


def test_selftest_reports_failures_with_the_reason(monkeypatch, tmp_path, capsys):
    log = tmp_path / "resultado.txt"
    monkeypatch.setenv("PALANTIR_SELFTEST_LOG", str(log))

    def broken(folder):
        raise RuntimeError("falta algo")

    monkeypatch.setattr(selftest, "_check", broken)
    assert selftest.run() == 1
    assert "falta algo" in capsys.readouterr().err
    assert "fallida" in log.read_text(encoding="utf-8") and "falta algo" in log.read_text(
        encoding="utf-8"
    )


def test_packaged_app_would_not_try_to_install_packages(monkeypatch):
    from palantir_nodes.ui.libraries_dialog import can_install

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert can_install() is False


# -- construcción -----------------------------------------------------------------------------------


def test_the_version_is_the_same_everywhere(build_release):
    toml = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert build_release.project_version() == __version__ == toml["project"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_a_tag_must_match_the_project_version(build_release):
    assert build_release.check_tag(f"v{__version__}") == __version__
    assert build_release.check_tag(f"refs/tags/v{__version__}") == __version__
    for wrong in ("v9.9.9", __version__, "v0.0.1-beta"):
        with pytest.raises(SystemExit, match="no corresponde"):
            build_release.check_tag(wrong)


@pytest.mark.parametrize(
    "system,machine,expected",
    [
        ("Windows", "AMD64", "windows-x64"),
        ("Linux", "x86_64", "linux-x64"),
        ("Darwin", "arm64", "macos-arm64"),
        ("Linux", "aarch64", "linux-arm64"),
    ],
)
def test_platform_tag_and_artifact_name(build_release, monkeypatch, system, machine, expected):
    monkeypatch.setattr(build_release.platform, "system", lambda: system)
    monkeypatch.setattr(build_release.platform, "machine", lambda: machine)
    assert build_release.platform_tag() == expected
    assert build_release.artifact_name("1.2.3") == f"PalantirNodes-v1.2.3-{expected}.zip"


def test_pyinstaller_arguments_bundle_assets_hook_and_launcher(build_release, tmp_path):
    args = build_release.pyinstaller_args(tmp_path / "logo.ico", tmp_path / "dist", tmp_path / "w")
    assert args[:2] == ["-m", "PyInstaller"] and "--windowed" in args and "--onefile" not in args
    assert args[args.index("--name") + 1] == "PalantirNodes"
    data = args[args.index("--add-data") + 1]
    source, _, target = data.rpartition(build_release.os.pathsep)
    assert Path(source, "play.svg").exists() and target == "palantir_nodes/ui/assets"
    hooks = Path(args[args.index("--additional-hooks-dir") + 1])
    assert (hooks / "hook-palantir_nodes.py").exists()
    assert "palantir_nodes" in args[args.index("--collect-submodules") + 1]
    assert args[args.index("--icon") + 1] == str(tmp_path / "logo.ico")
    assert Path(args[-1]).name == "launcher.py" and Path(args[-1]).exists()
    assert "--module-collection-mode" not in args  # no existe como opción de línea de comandos
    assert "--icon" not in build_release.pyinstaller_args(None, tmp_path, tmp_path)


def test_the_hook_collects_the_sources_the_exporter_needs():
    text = (ROOT / "packaging" / "hooks" / "hook-palantir_nodes.py").read_text(encoding="utf-8")
    assert 'module_collection_mode = "pyz+py"' in text
    assert "inspect.getsource" in text


def test_the_icon_is_drawn_from_the_logo(build_release, tmp_path):
    icon = build_release.make_icon(tmp_path / "palantir")
    assert icon is not None and icon.exists() and icon.stat().st_size > 1000
    assert icon.suffix == (".ico" if sys.platform == "win32" else ".png")


def test_documents_are_added_next_to_the_executable(build_release, tmp_path):
    build_release.add_documents(tmp_path, "1.2.3")
    assert (
        (tmp_path / "LICENSE")
        .read_text(encoding="utf-8")
        .startswith("                    GNU GENERAL")
    )
    assert (tmp_path / "THIRD_PARTY_NOTICES.md").exists()
    leeme = (tmp_path / "LEEME.txt").read_bytes().decode("utf-8")
    assert "Palantir Nodes 1.2.3" in leeme and "\r\n" in leeme  # se abre bien en el Bloc de notas
    assert "Windows protegió tu PC" in leeme and "tree/v1.2.3" in leeme
    assert build_release.executable_name() in leeme


def test_checksum_matches_the_file(build_release, tmp_path):
    path = tmp_path / "archivo.bin"
    path.write_bytes(b"palantir" * 100_000)
    assert build_release.sha256_of(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_selftest_of_a_missing_or_failing_executable_stops_the_build(build_release, tmp_path):
    with pytest.raises((SystemExit, OSError)):
        build_release.selftest(tmp_path)  # no hay ejecutable


# -- notas de la release ----------------------------------------------------------------------------

CHANGELOG = """# Cambios

## [Sin publicar]

## [0.2.0] - 2026-11-01
Novedades de la 0.2.0.

### Añadido
- Algo.

## [0.1.0] - 2026-10-28
Primera versión.
"""


def test_extract_section(release_notes):
    assert release_notes.extract_section(CHANGELOG, "0.2.0") == (
        "Novedades de la 0.2.0.\n\n### Añadido\n- Algo."
    )
    assert release_notes.extract_section(CHANGELOG, "0.1.0") == "Primera versión."  # la última
    assert release_notes.extract_section(CHANGELOG, "0.3.0") is None
    assert release_notes.extract_section(CHANGELOG, "0.2") is None  # la versión exacta
    assert release_notes.extract_section(CHANGELOG, "Sin publicar") == ""


def test_notes_include_the_section_the_download_steps_and_the_source_link(release_notes):
    notes = release_notes.build_notes(CHANGELOG, "v0.2.0", "PalantirNodes-v0.2.0-windows-x64.zip")
    assert notes.startswith("## Palantir Nodes 0.2.0\n\nNovedades de la 0.2.0.")
    assert "PalantirNodes-v0.2.0-windows-x64.zip" in notes and "Windows protegió tu PC" in notes
    assert "/tree/v0.2.0)" in notes and ".sha256" in notes


def test_notes_refuse_a_version_without_changelog_entry(release_notes):
    with pytest.raises(SystemExit, match="CHANGELOG.md no tiene"):
        release_notes.build_notes(CHANGELOG, "v0.3.0", "x.zip")
    with pytest.raises(SystemExit, match="CHANGELOG.md no tiene"):
        release_notes.build_notes("## [0.3.0]\n\n## [0.2.0]\ntexto", "v0.3.0", "x.zip")  # vacía


def test_the_changelog_describes_the_current_version(release_notes):
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    section = release_notes.extract_section(changelog, __version__)
    assert section and len(section) > 200  # hay que escribirlo antes de publicar


def test_release_notes_command_writes_the_file(release_notes, tmp_path, capsys):
    out = tmp_path / "notas.md"
    assert release_notes.main(["--tag", f"v{__version__}", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert f"Palantir Nodes {__version__}" in text and "windows-x64.zip" in text
    with pytest.raises(SystemExit):
        release_notes.main(["--tag", "v99.0.0", "--out", str(out)])


# -- flujos de GitHub Actions ---------------------------------------------------------------------------


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_release_workflow_triggers_on_version_tags_and_can_publish():
    text = workflow("release.yml")
    assert 'tags: ["v*"]' in text and "workflow_dispatch" in text
    assert "contents: write" in text and "softprops/action-gh-release@v2" in text
    assert "needs: test" in text and "runs-on: windows-latest" in text
    assert "--check-tag" in text and "tools/release_notes.py" in text and "body_path" in text
    assert "dist-release/*" in text and "upload-artifact" in text
    assert re.search(
        r"if: startsWith\(github.ref, 'refs/tags/v'\)\s+uses: softprops", text
    )  # solo con etiqueta


def test_ci_workflow_runs_lint_and_tests_on_changes():
    text = workflow("ci.yml")
    assert "pull_request" in text and "branches: [main]" in text
    assert "ruff check" in text and "pytest" in text and "QT_QPA_PLATFORM: offscreen" in text
    assert "contents: read" in text  # solo lectura: no publica nada


@pytest.mark.parametrize("name", ["ci.yml", "release.yml"])
def test_workflows_pin_action_versions_and_reference_existing_files(name):
    text = workflow(name)
    for action in re.findall(r"uses:\s*([^\s]+)", text):
        assert re.search(r"@v\d+$", action), action  # nunca @main ni sin versión
    for script in re.findall(r"python (tools/[\w./]+|packaging/[\w./]+)", text):
        assert (ROOT / script).exists(), script
    assert 'python-version: "3.13"' in text


def test_the_release_workflow_installs_what_the_build_needs():
    text = workflow("release.yml")
    assert '-e ".[network]" pyinstaller' in text  # los nodos WebSocket van dentro del programa
    assert "mediapipe" not in text.lower()  # MediaPipe no se empaqueta (pesaría demasiado)


def test_project_links_point_to_the_repository():
    toml = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = toml["project"]["urls"]
    assert urls["Releases"].endswith("/MorionTutoriales/Palantir-Nodes/releases")
    assert set(urls) >= {"Homepage", "Repository", "Issues", "Changelog", "Releases"}


def test_readme_explains_how_to_download():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Descargar" in text and "/releases/latest" in text and "PalantirNodes.exe" in text
    assert "Windows protegió tu PC" in text
    assert "docs/publicar.md" in text and (ROOT / "docs" / "publicar.md").exists()
    assert "actions/workflows/ci.yml" in text  # la insignia de las pruebas


def test_release_output_is_ignored_by_git():
    assert "/dist-release/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
