"""Funciones auxiliares que el script exportado incluye cuando las necesita.

Las que también usa el motor se copian con ``inspect.getsource`` desde su definición
original, de modo que el motor y el script ejecutan exactamente el mismo código y no
pueden divergir.
"""

from __future__ import annotations

import inspect
import textwrap
from dataclasses import dataclass

from palantir_nodes.media import capture
from palantir_nodes.nodes.library import _cv
from palantir_nodes.nodes.library.inputs import read_image


def _source(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn)).rstrip()


@dataclass(frozen=True)
class Helper:
    source: str
    deps: tuple[str, ...] = ()


_READ_FLAGS = """_READ_FLAGS = {
    "color": cv2.IMREAD_COLOR,
    "grayscale": cv2.IMREAD_GRAYSCALE,
    "unchanged": cv2.IMREAD_UNCHANGED,
}"""

_SAVE_IMAGE = '''def save_image(img: np.ndarray, path: str) -> None:
    """Guarda una imagen en disco (admite rutas con caracteres no ASCII)."""
    ext = os.path.splitext(path)[1].lower()
    if not ext:
        raise ValueError("El archivo de destino necesita extensión (.png, .jpg…)")
    ok, buffer = cv2.imencode(ext, img)
    if not ok:
        raise ValueError(f"No se pudo codificar la imagen como {ext}")
    buffer.tofile(path)'''

# El orden de este diccionario es el orden de emisión (las dependencias van antes).
HELPERS: dict[str, Helper] = {
    "to_uint8": Helper(_source(_cv.to_uint8)),
    "read_image": Helper(_READ_FLAGS + "\n\n\n" + _source(read_image), ("to_uint8",)),
    "as_gray": Helper(_source(_cv.as_gray)),
    "as_bgr": Helper(_source(_cv.as_bgr)),
    "match": Helper(_source(_cv.match), ("as_bgr",)),
    "save_image": Helper(_SAVE_IMAGE),
    "open_video_capture": Helper(_source(capture.open_video_capture)),
    "open_camera_capture": Helper(_source(capture.open_camera_capture)),
    "read_frame": Helper(_source(capture.read_frame)),
    "open_video_writer": Helper(_source(capture.open_video_writer)),
}


def resolve(requested: set[str]) -> list[str]:
    """Nombres de helpers a emitir (con dependencias), en orden de emisión."""
    needed: set[str] = set()

    def add(name: str) -> None:
        if name not in HELPERS:
            raise KeyError(f"Helper desconocido: {name}")
        if name not in needed:
            needed.add(name)
            for dep in HELPERS[name].deps:
                add(dep)

    for name in requested:
        add(name)
    return [name for name in HELPERS if name in needed]
