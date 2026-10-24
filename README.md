# Palantir Nodes

Editor visual de nodos para Python y OpenCV, inspirado en el Shader Editor de Blender.

## Instalación (Windows)

Requiere Python 3.12 o superior.

```bash
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Ejecutar

```bash
.venv\Scripts\python -m palantir_nodes
```

## Pruebas y lint

```bash
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check src tests
```

## Arquitectura

| Paquete | Responsabilidad | Depende de Qt |
|---|---|---|
| `core/` | Grafo lógico, tipos de socket, validación, orden topológico, errores | No |
| `nodes/` | Contrato `NodeDefinition`, especificaciones, registro, biblioteca | No |
| `ui/editor/` | Escena, vista, nodos, sockets, conexiones, comandos undo/redo | Sí |
| `engine/` | Plan inmutable del grafo, ejecutor con caché y errores por nodo | No |
| `media/` | Apertura y lectura de video, cámaras y escritores (compartido con el script exportado) | No |
| `persistence/` | Formato JSON versionado, validación, migraciones y lectura/escritura atómica | No |
| `codegen/` | Generador de scripts Python y helpers compartidos con el motor | No |
| `ui/properties/` | Panel de propiedades y widgets por tipo de parámetro | Sí |
| `ui/viewer/` | Visor de imágenes con zoom y desplazamiento | Sí |

La interfaz nunca modifica el grafo directamente: `EditorController` empuja comandos
(`QUndoCommand`) que cambian el `Graph`, y la escena se actualiza a partir de los eventos
del grafo.

Para añadir un nodo, crea una subclase de `NodeDefinition` decorada con `@register_node`
(o publícala como plugin en el grupo de entry points `palantir_nodes.nodes`).

## Estado: Fases 1 a 5 y guardado de proyectos (Fase 6, parte 1)

### Implementado

- **Editor:** tema oscuro, cuadrícula, zoom, desplazamiento, menú y buscador de nodos,
  conexiones Bézier validadas (tipos, ciclos, una por entrada), selección múltiple,
  duplicar/copiar/pegar/eliminar y deshacer/rehacer de todo.
- **Motor** (`engine/`, sin Qt): orden topológico, resultados entre nodos con conversiones
  implícitas explícitas, caché por contenido (solo se recalculan los nodos afectados por
  un cambio, incluida la fecha del archivo de imagen) y errores aislados por nodo: un
  nodo que falla marca en rojo ese nodo y en ámbar los que dependen de él; el resto del
  grafo se sigue calculando.
- **Ejecución fuera del hilo de la interfaz** (`QThread`) sobre una copia del grafo. Si se
  piden varias ejecuciones mientras se procesa, se colapsan en una sola.
- **40 nodos con procesamiento real:** entradas (Load Image, Number, Integer, Boolean,
  Color), imagen (Grayscale, Gaussian/Median Blur, Threshold, Adaptive Threshold, Canny,
  Resize, Crop, Rotate, Flip, HSV, InRange, Erode, Dilate, Morphological, Find/Draw
  Contours), matemáticas (Add, Subtract, Multiply, Divide, Clamp, Map Range, Minimum,
  Maximum, Compare), composición (Blend, Add Weighted, Bitwise AND/OR/NOT, Mask, Merge/Split
  Channels) y salidas (Image Viewer, Save Image).
- **Visor de imágenes** con zoom (rueda), desplazamiento, doble clic para ajustar, resolución,
  canales y tiempos. Muestra el nodo seleccionado o, si no hay selección, el primer Image Viewer.
- **Ejecución:** `F5` ejecuta; **Auto** (activado por defecto) re-ejecuta al cambiar el grafo.
  Save Image solo escribe en disco con `F5`, nunca en la ejecución automática.

- **Exportar a Python** (`Ctrl+E`): genera un `.py` independiente (solo OpenCV y NumPy) a partir
  del mismo plan que usa el motor; cada nodo aporta su código con `generate_code`. El script
  tiene imports, helpers, `main()` y `if __name__ == "__main__":`, nombres de variable únicos,
  parámetros conservados, y solo incluye lo que alimenta una salida. Si falla, el error indica
  el nodo (`Error en el nodo 'Load Image': ...`). `--no-show` evita abrir ventanas. Al exportar
  se avisa de problemas (entrada sin conectar, archivo sin elegir) y se seleccionan los nodos.
  Las rutas se escriben tal cual están en el grafo (las relativas lo son al directorio actual).

- **Video y tiempo real:** nodos Load Video, Webcam, Video Viewer y Save Video. Si el grafo
  tiene una fuente, `F5` inicia el tiempo real: un `QThread` procesa fotograma a fotograma
  (los archivos a su velocidad; las cámaras al ritmo del dispositivo). **Pausa** (`F6`) y
  **Detener** (`Shift+F5`) controlan la sesión; los cambios en el grafo se aplican en vivo sin
  reabrir las fuentes que no cambiaron. El visor muestra FPS y tiempo por fotograma. Si el
  procesamiento es más lento que la fuente se descartan fotogramas: nunca se acumulan.
  Cámaras, archivos y escritores se liberan al detener, al terminar el video, ante un error
  y al cerrar la ventana. Save Video solo escribe en tiempo real iniciado con `F5`.
- **Exportar con video:** si hay fuentes, el script procesa en un bucle (`--max-frames N`,
  `--no-show`, `q` cierra las ventanas), abre los recursos antes del bucle y los libera en
  `finally`. Un error indica el nodo que falló.

- **Proyectos JSON** (`Ctrl+O`, `Ctrl+S`, `Ctrl+Shift+S`; también `python -m palantir_nodes proyecto.json`):
  guarda versión del formato, nodos (id, tipo, posición, parámetros, valores de entradas),
  conexiones, zoom y centro del editor, y el estado de Auto. El título muestra el nombre y `*`
  si hay cambios; al cerrar o crear un proyecto nuevo pregunta si guardar.
  - **Escritura atómica:** se escribe a un temporal y se renombra; un fallo (disco lleno, dato
    inválido) deja intacto el archivo anterior.
  - **Validación:** un archivo ilegible, vacío, que no sea JSON, que no sea de Palantir Nodes o
    de una versión más nueva se rechaza con un mensaje claro y **el proyecto actual no se toca**.
  - **Tolerancia:** parámetros inválidos vuelven a su valor por defecto, y nodos o conexiones
    inválidos se omiten; todo se informa en un diálogo de avisos.
  - **Nodos desconocidos** (p. ej. de un plugin no instalado): no se muestran, pero se conservan
    y se vuelven a escribir al guardar, para no perder información.
  - **Migraciones:** `persistence/format.py` tiene la tabla `MIGRATIONS` (v N → v N+1) para
    cuando cambie el formato.
  - Las rutas de archivos de imagen/video se guardan tal cual (absolutas si así se eligieron).

### No implementado todavía

- **Tipo de socket `Video`:** Load Video y Webcam entregan un fotograma (`Image`) por
  iteración; el tipo `Video` como flujo completo no se usa todavía.
- **Webcam probada solo con simulación:** no hay cámara en el entorno de pruebas; la lectura
  de archivos de video sí está verificada de punta a punta.
- **Frames/grupos visuales, previsualización dentro del nodo, edición de valores dentro del
  nodo, preferencias** (resto de la Fase 6).

Las acciones de la barra superior que aún no funcionan aparecen deshabilitadas.

### Atajos (con el foco en el editor)

| Acción | Atajo |
|---|---|
| Añadir nodo | Clic derecho en vacío / `Shift+A` |
| Buscar nodo | `Ctrl+F` |
| Seleccionar / añadir a la selección | Clic / `Shift+clic`, arrastre en vacío |
| Seleccionar todo / nada | `A` o `Ctrl+A` / `Alt+A` |
| Duplicar / Copiar / Pegar | `Shift+D` / `Ctrl+C` / `Ctrl+V` (en el cursor) |
| Eliminar | `X` / `Supr` |
| Deshacer / Rehacer | `Ctrl+Z` / `Ctrl+Shift+Z` o `Ctrl+Y` |
| Encuadrar todo | `Inicio` |
| Cancelar conexión en curso | `Esc` o clic derecho |

### Criterios de aceptación (Fases 1-5)

1. `python -m palantir_nodes` abre la ventana sin errores.
2. Se puede construir Load Image → Grayscale → Threshold → Find Contours → Draw Contours →
   Image Viewer, y el visor muestra el resultado; cambiar un parámetro lo actualiza.
3. Un nodo que falla (archivo inexistente, división entre cero…) se marca con su motivo y no
   detiene el resto del grafo.
4. Las conexiones inválidas se rechazan con su motivo; deshacer/rehacer funcionan.
5. La interfaz sigue respondiendo mientras se procesa.
6. Exportar a Python un grafo y ejecutar el script produce las mismas imágenes que el motor
   (las pruebas lo comprueban nodo por nodo y con cadenas de matemáticas y conversiones).
7. Load Video → nodos → Video Viewer reproduce a la velocidad del archivo con FPS, se puede
   pausar y detener, y la interfaz sigue respondiendo.
8. Tras detener, terminar o cerrar, el archivo de video puede borrarse (no queda abierto).
9. Guardar y reabrir un proyecto reproduce el mismo grafo, zoom y posición; un archivo dañado
   no destruye el proyecto abierto ni el archivo guardado anterior.
10. `pytest` pasa (278 pruebas: modelo, validación, motor, nodos, exportación, tiempo real,
    persistencia y UI real).
