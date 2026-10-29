"""Escribe las notas de una release a partir de CHANGELOG.md.

Uso (lo ejecuta el flujo de GitHub Actions)::

    python tools/release_notes.py --tag v0.1.0 --out release-notes.md

Falla si CHANGELOG.md no tiene una sección para esa versión: así no se publica una release
sin explicar qué trae.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/MorionTutoriales/Palantir-Nodes"

FOOTER = """
---

### Cómo usarlo

1. Descarga **{asset}** (más abajo, en *Assets*) y descomprímelo donde quieras.
2. Abre **PalantirNodes.exe**.

Windows puede avisar con «Windows protegió tu PC» porque el programa es libre pero no está
firmado digitalmente: pulsa *Más información* → *Ejecutar de todas formas*. La suma de
comprobación (SHA-256) está en el archivo `.sha256` de esta release.

Esta versión incluye el editor, el motor, la exportación a Python y los nodos de red
(WebSocket y TCP). MediaPipe y la instalación de paquetes desde la aplicación necesitan un Python
instalado: para eso, instala desde el código fuente (consulta el
[README]({repository}#instalación)).

Código fuente de esta versión: [{tag}]({repository}/tree/{tag}) · Licencia GPL-3.0-or-later.
"""


def extract_section(changelog: str, version: str) -> str | None:
    """El texto de la sección ``## [version]`` de un CHANGELOG, o ``None`` si no existe."""
    heading = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n", re.M)
    match = heading.search(changelog)
    if match is None:
        return None
    following = re.search(r"^## ", changelog[match.end() :], re.M)
    end = match.end() + following.start() if following else len(changelog)
    return changelog[match.end() : end].strip()


def build_notes(changelog: str, tag: str, asset: str) -> str:
    version = tag.removeprefix("refs/tags/").removeprefix("v")
    section = extract_section(changelog, version)
    if not section:
        raise SystemExit(
            f"CHANGELOG.md no tiene una sección «## [{version}]» con contenido: añádela antes de "
            "publicar la release"
        )
    footer = FOOTER.format(asset=asset, repository=REPOSITORY, tag=f"v{version}")
    return f"## Palantir Nodes {version}\n\n{section}\n{footer}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Notas de la release desde CHANGELOG.md")
    parser.add_argument("--tag", required=True, help="etiqueta, p. ej. v0.1.0")
    parser.add_argument("--out", type=Path, required=True, help="archivo de salida")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).parent))
    from build_release import artifact_name

    version = args.tag.removeprefix("refs/tags/").removeprefix("v")
    notes = build_notes(
        args.changelog.read_text(encoding="utf-8"), args.tag, artifact_name(version)
    )
    args.out.write_text(notes, encoding="utf-8", newline="\n")
    print(f"Notas de la release {version} escritas en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
