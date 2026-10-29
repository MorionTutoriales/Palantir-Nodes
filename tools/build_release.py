"""Construye la versión descargable de Palantir Nodes (la que se publica en GitHub Releases).

Genera, con PyInstaller, una carpeta con el ejecutable y todo lo que necesita (no hace falta tener
Python instalado), la comprime en un ``.zip`` con su suma de comprobación y comprueba que el
ejecutable arranca (``--selftest``).

Uso, desde la raíz del proyecto (con PyInstaller instalado: ``pip install pyinstaller``)::

    .venv\\Scripts\\python tools\\build_release.py            # compila y comprueba
    .venv\\Scripts\\python tools\\build_release.py --print-name  # solo muestra el nombre del .zip
    .venv\\Scripts\\python tools\\build_release.py --check-tag v0.1.0

El resultado queda en ``dist-release/``. Solo se ha probado en Windows.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
APP_NAME = "PalantirNodes"
REPOSITORY = "https://github.com/MorionTutoriales/Palantir-Nodes"

LEEME = """Palantir Nodes {version}
Editor visual de nodos para procesar imágenes y video con Python y OpenCV.

Cómo usarlo
-----------
1. Descomprime esta carpeta donde quieras (no la ejecutes desde dentro del .zip).
2. Abre {executable}.
3. Si Windows muestra «Windows protegió tu PC», pulsa «Más información» y luego «Ejecutar de
   todas formas»: el programa es libre pero no está firmado digitalmente.

Qué incluye y qué no
--------------------
Incluye el editor, el motor, la exportación a Python y los nodos de red (WebSocket y TCP).
No incluye MediaPipe ni la instalación de paquetes desde la aplicación (necesitan un Python
instalado): para eso, instala Palantir Nodes desde el código fuente.

Licencia y código fuente
------------------------
Palantir Nodes es software libre bajo la GNU General Public License v3.0 o posterior (archivo
LICENSE). Los avisos de los componentes de terceros están en THIRD_PARTY_NOTICES.md.
Código fuente de esta versión: {repository}/tree/v{version}
"""


# -- versión y nombres --------------------------------------------------------------------------


def project_version() -> str:
    """La versión del proyecto, comprobando que coinciden el paquete y ``pyproject.toml``."""
    package = (SRC / "palantir_nodes" / "__init__.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    in_code = re.search(r'__version__\s*=\s*"([^"]+)"', package)
    in_toml = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    if not in_code or not in_toml:
        raise SystemExit("No se encontró la versión en __init__.py o en pyproject.toml")
    if in_code.group(1) != in_toml.group(1):
        raise SystemExit(
            f"La versión no coincide: __init__.py dice {in_code.group(1)} y "
            f"pyproject.toml {in_toml.group(1)}"
        )
    return in_code.group(1)


def check_tag(tag: str) -> str:
    """Comprueba que la etiqueta de git (``v0.1.0``) corresponde a la versión del proyecto."""
    version = project_version()
    if tag.removeprefix("refs/tags/") != f"v{version}":
        raise SystemExit(
            f"La etiqueta '{tag}' no corresponde a la versión del proyecto ({version}): "
            f"cambia la versión o usa la etiqueta v{version}"
        )
    return version


def platform_tag() -> str:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system(), platform.system().lower()
    )
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    return f"{system}-{arch}"


def artifact_name(version: str) -> str:
    return f"{APP_NAME}-v{version}-{platform_tag()}.zip"


def executable_name() -> str:
    return f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME


# -- PyInstaller ----------------------------------------------------------------------------------


def pyinstaller_args(icon: Path | None, dist: Path, work: Path) -> list[str]:
    """Argumentos de PyInstaller para empaquetar la aplicación (carpeta, sin consola)."""
    assets = SRC / "palantir_nodes" / "ui" / "assets"
    args = [
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--paths",
        str(SRC),
        "--distpath",
        str(dist),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work / "spec"),
        # Los iconos y el logotipo son archivos de datos del paquete.
        "--add-data",
        f"{assets}{os.pathsep}palantir_nodes/ui/assets",
        # Módulos que el programa importa por su nombre en tiempo de ejecución (nodos, librerías).
        "--collect-submodules",
        "palantir_nodes",
        # El exportador a Python lee el código fuente de sus propias funciones (inspect.getsource):
        # este gancho incluye los módulos de la aplicación también como archivos .py.
        "--additional-hooks-dir",
        str(ROOT / "packaging" / "hooks"),
    ]
    if importlib.util.find_spec("websockets") is not None:
        args += ["--collect-submodules", "websockets"]  # los nodos WebSocket
    if icon is not None:
        args += ["--icon", str(icon)]
    args.append(str(ROOT / "packaging" / "launcher.py"))
    return args


def make_icon(target: Path) -> Path | None:
    """Dibuja el logotipo como icono de la aplicación. ``None`` si no se pudo (no es grave)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QByteArray, Qt
        from PySide6.QtGui import QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        app = QGuiApplication.instance() or QGuiApplication([])
        svg = (SRC / "palantir_nodes" / "ui" / "assets" / "logo.svg").read_bytes()
        renderer = QSvgRenderer(QByteArray(svg))
        image = QImage(256, 256, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        suffix = ".ico" if sys.platform == "win32" else ".png"
        icon = target.with_suffix(suffix)
        if not image.save(str(icon)):
            return None
        del app
        return icon
    except Exception as exc:  # sin icono la aplicación funciona igual
        print(f"Aviso: no se pudo crear el icono ({exc})", file=sys.stderr)
        return None


# -- construcción ---------------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def add_documents(folder: Path, version: str) -> None:
    """Licencia, avisos de terceros y un LEEME dentro de la carpeta que se distribuye."""
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, folder / name)
    text = LEEME.format(version=version, executable=executable_name(), repository=REPOSITORY)
    (folder / "LEEME.txt").write_text(text, encoding="utf-8", newline="\r\n")


def selftest(folder: Path) -> None:
    """Ejecuta el programa empaquetado con ``--selftest`` y exige que termine bien."""
    executable = folder / executable_name()
    with tempfile.TemporaryDirectory(prefix="palantir_check_") as scratch:
        log = Path(scratch) / "resultado.txt"
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PALANTIR_SELFTEST_LOG": str(log)}
        process = subprocess.run(
            [str(executable), "--selftest"], env=env, capture_output=True, timeout=300
        )
        report = log.read_text(encoding="utf-8") if log.exists() else "(sin resultado)"
    if process.returncode != 0 or "correcta" not in report:
        raise SystemExit(
            f"El programa empaquetado no pasó la autocomprobación (código "
            f"{process.returncode}):\n{report}"
        )
    print(f"Autocomprobación del ejecutable: {report.strip()}")


def build(out: Path, *, run_selftest: bool = True) -> Path:
    """Compila, comprime y comprueba. Devuelve la ruta del ``.zip``."""
    version = project_version()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="palantir_build_") as scratch:
        work = Path(scratch)
        dist = work / "dist"
        icon = make_icon(work / "palantir")
        command = [sys.executable, *pyinstaller_args(icon, dist, work)]
        print("$", " ".join(command), flush=True)
        subprocess.run(command, check=True, cwd=ROOT)
        folder = dist / APP_NAME
        if not (folder / executable_name()).exists():
            raise SystemExit(f"PyInstaller no generó {folder / executable_name()}")
        add_documents(folder, version)
        if run_selftest:
            selftest(folder)
        archive = out / artifact_name(version)
        base = shutil.make_archive(str(archive.with_suffix("")), "zip", dist, APP_NAME)
        assert Path(base) == archive
    checksum = archive.with_name(archive.name + ".sha256")
    checksum.write_text(f"{sha256_of(archive)}  {archive.name}\n", encoding="utf-8", newline="\n")
    size = archive.stat().st_size / 1_000_000
    print(f"Listo: {archive} ({size:.0f} MB) y {checksum.name}")
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construye la versión descargable.")
    parser.add_argument("--out", type=Path, default=ROOT / "dist-release", help="carpeta de salida")
    parser.add_argument("--skip-selftest", action="store_true", help="no ejecutar el programa")
    parser.add_argument("--print-name", action="store_true", help="solo mostrar el nombre del .zip")
    parser.add_argument(
        "--check-tag", metavar="ETIQUETA", help="comprobar que coincide con la versión"
    )
    args = parser.parse_args(argv)
    if args.check_tag:
        print(check_tag(args.check_tag))
        return 0
    if args.print_name:
        print(artifact_name(project_version()))
        return 0
    build(args.out, run_selftest=not args.skip_selftest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
