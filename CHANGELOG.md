# Cambios

Todos los cambios importantes de Palantir Nodes. Cada versión publicada tiene su sección
`## [x.y.z]`: el texto de esa sección es el que aparece en la release de GitHub.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones
siguen [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

## [0.1.0] - 2026-10-28

Primera versión pública.

### Editor
- Editor visual de nodos con tema oscuro, cuadrícula, zoom, deshacer/rehacer, selección múltiple,
  frames para agrupar nodos y chincheta para fijar el visor en un nodo.
- Edición dentro del nodo (clic, arrastre, deslizador, listas, color) y miniaturas de los
  resultados; cualquier parámetro numérico se puede conectar a otro nodo.
- Panel **Nodos** con buscador (doble clic o arrastrar al editor) y buscador al soltar una
  conexión en un espacio vacío, como en Blender.
- Interfaz con iconos ([Lucide](https://lucide.dev), ISC), barra de vista y cuatro **skins**
  (Oscuro, Medianoche, Bosque y Claro) que no cambian el aspecto de los nodos.

### Motor y nodos
- 61 nodos: entradas (imagen, video, webcam, números, deslizador, Tick), imagen (filtros,
  umbrales, contornos, color), conversión, matemáticas, composición y salidas.
- Caché por contenido, errores aislados por nodo y procesamiento fuera del hilo de la interfaz.
- Tiempo real con webcam y video (pausa, detener, FPS).

### De la idea al programa
- **Exportar a Python** un script independiente que da el mismo resultado que el editor.
- **Compilar a ejecutable** (PyInstaller) desde la propia aplicación.
- Proyectos JSON versionados con escritura atómica.

### Ampliable
- **Nodos personalizados** escritos como funciones de Python (entradas y salidas detectadas
  solas, rutas de importación propias).
- **Librerías opcionales por proyecto:** red por WebSocket y TCP, y MediaPipe (manos, cuerpo y
  rostros) con nodos para convertir los resultados a JSON.

### Descarga
- Versión para Windows en la sección Releases: se descomprime y se abre, sin instalar Python.
  Incluye el editor y los nodos de red; MediaPipe requiere instalar desde el código fuente.
