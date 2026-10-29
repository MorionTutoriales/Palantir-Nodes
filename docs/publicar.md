# Publicar una versión (Releases de GitHub)

Una *release* es una versión con su `.zip` descargable en la pestaña **Releases** del repositorio.
Se construye sola: basta con subir una **etiqueta** `v*` y GitHub Actions hace el resto.

## Qué hace el flujo automático

El archivo [`.github/workflows/release.yml`](../.github/workflows/release.yml) se ejecuta al subir
una etiqueta como `v0.2.0` y, en una máquina Windows de GitHub:

1. **Prueba** el código (`ruff` y todas las pruebas). Si algo falla, no se publica nada.
2. Comprueba que la etiqueta coincide con la versión del proyecto.
3. Escribe las notas de la release con la sección de esa versión de [`CHANGELOG.md`](../CHANGELOG.md).
4. **Construye** `PalantirNodes-vX.Y.Z-windows-x64.zip` con PyInstaller, abre el programa
   resultante con `--selftest` para comprobar que arranca y calcula la suma SHA-256.
5. **Publica** la release con el `.zip` y el `.sha256`.

Además, el flujo [`ci.yml`](../.github/workflows/ci.yml) revisa y prueba cada cambio que subes a
`main` y cada *pull request*.

## Pasos para sacar una versión nueva

1. **Sube la versión** en los dos sitios (deben coincidir; el flujo lo comprueba):
   - `src/palantir_nodes/__init__.py` → `__version__ = "0.2.0"`
   - `pyproject.toml` → `version = "0.2.0"`
2. **Escribe los cambios** en `CHANGELOG.md`: renombra «Sin publicar» a `## [0.2.0] - AAAA-MM-DD`
   (y deja una sección «Sin publicar» vacía encima). Sin esta sección el flujo se detiene.
3. **Súbelo** y crea la etiqueta:

   ```bash
   git add -A
   git commit -m "Versión 0.2.0"
   git push
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. Mira la pestaña **Actions**: unos 10-15 minutos después aparece la release en **Releases**.
   Puedes editar su texto desde GitHub.

Una etiqueta con guion (`v0.3.0-beta1`) se publica como **versión preliminar** (*pre-release*).

## Probar la construcción sin publicar

- **En tu equipo:** `.venv\Scripts\python tools\build_release.py` (necesita `pip install
  pyinstaller`). Deja el `.zip` en `dist-release/` y comprueba que el programa arranca.
- **En GitHub:** pestaña *Actions* → *Release* → *Run workflow*. Construye y deja el `.zip` como
  *artefacto* de la ejecución, sin crear ninguna release.

## Si algo sale mal

- **Se publicó una release defectuosa:** bórrala desde Releases (y la etiqueta con
  `git push origin :refs/tags/v0.2.0`), corrige y vuelve a etiquetar.
- **«La etiqueta no corresponde a la versión»:** la versión de los dos archivos del paso 1 no es la
  de la etiqueta.
- **«CHANGELOG.md no tiene una sección…»:** falta el paso 2.

## Qué lleva (y qué no) la versión descargable

Lleva el editor, el motor, el exportador y los nodos de red WebSocket y TCP, más la licencia, los
avisos de terceros y un `LEEME.txt`. **No** lleva MediaPipe (haría el archivo mucho más pesado) ni
puede instalar paquetes desde la aplicación, porque no hay un Python con `pip` detrás. Quien los
necesite instala desde el código fuente.

Como el programa es GPL-3.0-or-later, el código fuente de cada versión debe estar disponible: lo
está en la propia etiqueta del repositorio, que las notas de la release enlazan.

## Sobre el aviso de Windows

El `.exe` no está firmado digitalmente, así que Windows SmartScreen puede avisar la primera vez.
Firmarlo exige un certificado de pago; mientras tanto, las notas explican cómo continuar y la suma
SHA-256 permite comprobar que la descarga es la publicada.
