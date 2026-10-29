"""Compilación del script exportado a un ejecutable con PyInstaller. No depende de Qt."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

# Paquetes con datos o librerías nativas que PyInstaller no encuentra solo con leer los import.
COLLECT_ALL = ("mediapipe",)


def pyinstaller_available() -> bool:
    try:
        return importlib.util.find_spec("PyInstaller") is not None
    except (ImportError, ValueError):
        return False


def safe_name(name: str) -> str:
    """Nombre válido para el ejecutable: letras, números, guion y guion bajo."""
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "_", name.strip()).strip("_")
    return cleaned or "grafo"


def executable_path(dist_dir: str | Path, name: str, onefile: bool = True) -> Path:
    """Dónde queda el ejecutable: ``dist/nombre.exe`` o, en carpeta, ``dist/nombre/nombre.exe``."""
    name = safe_name(name)
    suffix = ".exe" if sys.platform == "win32" else ""
    base = Path(dist_dir) if onefile else Path(dist_dir) / name
    return base / f"{name}{suffix}"


def packages_to_collect(code: str) -> list[str]:
    """Paquetes del script que necesitan ``--collect-all`` (p. ej. MediaPipe)."""
    return [pkg for pkg in COLLECT_ALL if re.search(rf"^\s*(from|import)\s+{pkg}\b", code, re.M)]


def pyinstaller_command(
    script: str | Path,
    name: str,
    dist_dir: str | Path,
    work_dir: str | Path,
    *,
    onefile: bool = True,
    console: bool = True,
    search_paths: list[str] | None = None,
    collect: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Programa y argumentos que compilan ``script`` con el Python de la aplicación."""
    args = [
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile" if onefile else "--onedir",
        "--console" if console else "--noconsole",
        "--name",
        safe_name(name),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(Path(work_dir) / "work"),
        "--specpath",
        str(Path(work_dir) / "spec"),
    ]
    for folder in search_paths or []:
        args += ["--paths", folder]
    for package in collect or []:
        args += ["--collect-all", package]
    args.append(str(script))
    return sys.executable, args
