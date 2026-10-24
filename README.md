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
| `codegen/` | Generador de scripts Python y helpers compartidos con el motor | No |
| `ui/properties/` | Panel de propiedades y widgets por tipo de parámetro | Sí |
| `ui/viewer/` | Visor de imágenes con zoom y desplazamiento | Sí |

La interfaz nunca modifica el grafo directamente: `EditorController` empuja comandos
(`QUndoCommand`) que cambian el `Graph`, y la escena se actualiza a partir de los eventos
del grafo.

Para añadir un nodo, crea una subclase de `NodeDefinition` decorada con `@register_node`
(o publícala como plugin en el grupo de entry points `palantir_nodes.nodes`).

## Estado: Fases 1 a 4 (editor, motor, procesamiento y exportación a Python)

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

### No implementado todavía

- **Video, webcam y tiempo real** (Fase 5): Load Video, Webcam, Video Viewer, Save Video,
  Detener, FPS. El visor solo muestra imágenes estáticas.
- **Guardar y abrir proyectos JSON**: pendiente.
- **Frames/grupos visuales, previsualización dentro del nodo, edición de valores dentro del
  nodo, preferencias** (Fase 6).

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

### Criterios de aceptación (Fases 1-4)

1. `python -m palantir_nodes` abre la ventana sin errores.
2. Se puede construir Load Image → Grayscale → Threshold → Find Contours → Draw Contours →
   Image Viewer, y el visor muestra el resultado; cambiar un parámetro lo actualiza.
3. Un nodo que falla (archivo inexistente, división entre cero…) se marca con su motivo y no
   detiene el resto del grafo.
4. Las conexiones inválidas se rechazan con su motivo; deshacer/rehacer funcionan.
5. La interfaz sigue respondiendo mientras se procesa.
6. Exportar a Python un grafo y ejecutar el script produce las mismas imágenes que el motor
   (las pruebas lo comprueban nodo por nodo y con cadenas de matemáticas y conversiones).
7. `pytest` pasa (203 pruebas: modelo, validación, motor, nodos, exportación y UI real).
