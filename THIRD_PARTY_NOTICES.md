# Avisos de terceros

Palantir Nodes se publica bajo la **GNU General Public License v3.0 o posterior** (ver
[LICENSE](LICENSE)). Incluye o usa los siguientes componentes de terceros, todos con licencias
compatibles con la GPL.

## Incluidos en este repositorio

| Componente | Uso | Licencia |
|---|---|---|
| [Lucide](https://lucide.dev) (`lucide-static` 1.61.0) | Los iconos de la interfaz, en `src/palantir_nodes/ui/assets/*.svg` | ISC (el texto completo está en `src/palantir_nodes/ui/assets/LICENSE-lucide.txt`; algunos iconos derivan de [Feather](https://feathericons.com), MIT) |

El logotipo (`src/palantir_nodes/ui/assets/logo.svg`) es obra del proyecto y se publica bajo la
misma licencia que él.

## Dependencias (no se incluyen, se instalan aparte)

| Paquete | Licencia |
|---|---|
| [PySide6](https://doc.qt.io/qtforpython-6/) (Qt for Python) | LGPL-3.0 |
| [OpenCV](https://opencv.org) (`opencv-python`) | Apache-2.0 |
| [NumPy](https://numpy.org) | BSD-3-Clause |
| [websockets](https://websockets.readthedocs.io) (opcional) | BSD-3-Clause |
| [MediaPipe](https://ai.google.dev/edge/mediapipe) (opcional) | Apache-2.0 |
| [PyInstaller](https://pyinstaller.org) (opcional, solo para compilar) | GPL-2.0 con excepción para los programas que genera |

Los modelos de MediaPipe se descargan de Google la primera vez que se usan; no forman parte de
este repositorio y se rigen por su propia licencia.
