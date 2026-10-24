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
| `ui/properties/` | Panel de propiedades y widgets por tipo de parámetro | Sí |

La interfaz nunca modifica el grafo directamente: `EditorController` empuja comandos
(`QUndoCommand`) que cambian el `Graph`, y la escena se actualiza a partir de los eventos
del grafo.

Para añadir un nodo, crea una subclase de `NodeDefinition` decorada con `@register_node`
(o publícala como plugin en el grupo de entry points `palantir_nodes.nodes`).

## Estado: Fase 1 (editor visual)

### Implementado

- Ventana con tema oscuro, editor central y paneles acoplables (Visor y Propiedades).
- Cuadrícula, zoom con la rueda (10 %–300 %) y desplazamiento con el botón central.
- Menú contextual por categorías y buscador de nodos.
- Conexiones Bézier arrastrando entre sockets en cualquier dirección, con vista previa
  verde o roja y el motivo del rechazo en la barra de estado.
- Validación de conexiones: entrada↔salida, tipos compatibles, conversiones explícitas,
  sin ciclos, una conexión por entrada (se reemplaza al soltar otra).
- Arrastrar desde una entrada conectada levanta la conexión; soltarla en vacío la elimina.
- Selección múltiple, mover, duplicar, copiar/pegar, eliminar nodos y conexiones.
- Deshacer/rehacer de todas las operaciones (los cambios seguidos de un mismo valor se
  agrupan en un solo paso).
- Panel de propiedades: números, deslizadores, casillas, listas, colores, vectores,
  rutas de archivo y textos.
- 19 tipos de nodo declarados (sockets y parámetros reales).

### No implementado todavía

- **Procesamiento de los nodos y visor** (Fase 3): los nodos no procesan nada todavía;
  el panel de propiedades lo indica.
- **Exportar a Python** (Fase 4), **video y tiempo real** (Fase 5).
- **Guardar y abrir proyectos JSON**: pendiente.
- **Frames/grupos visuales, edición de valores dentro del nodo, preferencias** (Fase 6).
- El resto de la biblioteca de nodos de la especificación.

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

### Criterios de aceptación de la Fase 1

1. `python -m palantir_nodes` abre la ventana sin errores.
2. Se pueden crear nodos desde el menú y el buscador, moverlos, conectarlos y eliminarlos.
3. Las conexiones inválidas (dos entradas, tipos incompatibles, ciclos) se rechazan y se
   muestra el motivo.
4. Deshacer y rehacer funcionan en crear, mover, conectar, reemplazar, eliminar, pegar y
   editar valores.
5. Los cambios en el panel de propiedades se reflejan en el nodo y viceversa (al deshacer).
6. `pytest` pasa (78 pruebas: modelo, validación, comandos y UI con eventos reales).
