# Referencia funcional

Detalle de cada función de Palantir Nodes, para consultar cuando haga falta. Para empezar a usar
la aplicación, ve al [README](../README.md); el catálogo completo de nodos está en
[nodos.md](nodos.md) y la guía de nodos escritos en Python en [nodos-personalizados.md](nodos-personalizados.md).

## Arquitectura

| Paquete | Responsabilidad | Depende de Qt |
|---|---|---|
| `core/` | Grafo lógico, tipos de socket, validación, orden topológico, errores | No |
| `nodes/` | Contrato `NodeDefinition`, especificaciones, registro, biblioteca | No |
| `customnodes/` | Nodos escritos en Python: análisis estático, ejecución, biblioteca | No |
| `libraries/` | Librerías adicionales por proyecto (hoy: red WebSocket) y su gestor | No |
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

## Funciones

### Funciones implementadas

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
- **47 nodos con procesamiento y exportación a Python:** los 44 de la especificación original
  (una prueba comprueba la lista completa) más `Integer`, `Vector2` y `Vector3`. Entradas (Load Image, Load Video,
  Webcam, Number, Integer, Boolean, Color), imagen (Grayscale, Gaussian/Median Blur,
  Threshold, Adaptive Threshold, Canny, Resize, Crop, Rotate, Flip, HSV, InRange, Erode,
  Dilate, Morphological, Find/Draw Contours), matemáticas (Add, Subtract, Multiply, Divide,
  Clamp, Map Range, Minimum, Maximum, Compare), composición (Blend, Add Weighted, Bitwise
  AND/OR/NOT, Mask, Merge/Split Channels) y salidas (Image Viewer, Video Viewer, Save Image,
  Save Video).
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

- **Frames (grupos visuales):** `Ctrl+J` envuelve los nodos seleccionados en un frame; también
  desde el menú de clic derecho ("Añadir frame aquí") o Editar. Se mueve arrastrando su
  **título** (lo acompañan los nodos y frames que contiene por completo, en un solo paso de
  deshacer) y se redimensiona con la **esquina inferior derecha**. Doble clic en el título o
  clic derecho → Renombrar / Cambiar color; el panel de propiedades edita título y color.
  Eliminar un frame **no** elimina sus nodos. El cuerpo del frame no captura el ratón, así que
  se pueden seleccionar y mover los nodos de dentro con normalidad. Los frames son solo
  visuales: no afectan al motor ni al script exportado. Se guardan en el proyecto (campo
  opcional `frames`; los proyectos anteriores siguen abriéndose).

- **Edición de valores dentro del nodo:** los campos que se ven en el nodo son editables.
  - **Casillas:** un clic las conmuta.
  - **Números** (enteros y decimales): clic para escribir (Enter confirma, Esc cancela, perder
    el foco confirma; se acepta coma decimal) o **arrastrar horizontalmente** para ajustar en
    vivo (400 px recorren todo el rango; con `Ctrl` o `Mayús`, ajuste fino ×0,1). Un arrastre
    es un único paso de deshacer.
  - **Vectores:** clic y escribir `1, 2, 3`.
  - **Listas:** clic abre un menú. **Colores:** clic abre el selector. **Archivos:** clic abre
    el diálogo de abrir/guardar.
  - Los valores fuera de rango se recortan, un texto inválido avisa y no cambia nada, y las
    entradas ya conectadas no se editan (su valor viene de otro nodo). Hacer clic en un campo
    deja ese nodo como única selección. El panel de propiedades sigue disponible y se mantiene
    sincronizado. Arrastrar el encabezado sigue moviendo el nodo.

- **Previsualización dentro del nodo:** los nodos que producen o reciben una imagen muestran
  una miniatura de su resultado al final del nodo (se ajusta a la proporción, sin ampliar más
  de 3 veces las imágenes diminutas). Las miniaturas se calculan en el hilo de trabajo, no en
  la interfaz. Los nodos con error o sin imagen no muestran ninguna. En tiempo real se
  actualizan unas 15 veces por segundo como máximo, sin frenar el procesamiento. Se activan
  o desactivan en **Ver → Previsualizaciones en los nodos** (el estado se guarda en el
  proyecto); desactivadas, ni siquiera se calculan.

- **Preferencias** (`Ctrl+,` o la barra superior; se guardan al aceptar y se aplican al instante):
  - **General:** reabrir el último proyecto al iniciar.
  - **Editor:** mostrar u ocultar la cuadrícula y velocidad del zoom de la rueda (1,05–1,50).
  - **Ejecución (valores para proyectos nuevos):** Auto, previsualizaciones en los nodos y máximo
    de miniaturas por segundo en tiempo real (5–30; este último se aplica incluso a una sesión
    en marcha). Un proyecto guardado conserva su propio Auto y previsualizaciones.
  - Se guardan en `%APPDATA%\PalantirNodes\preferences.json` (Windows) o
    `~/.config/palantir-nodes/` (otros), de forma atómica. Un archivo ausente, dañado o con valores
    inválidos nunca impide arrancar: se usan los valores por defecto (los inválidos se corrigen
    uno a uno) y se avisa en la barra de estado. La variable `PALANTIR_NODES_CONFIG_DIR` cambia la
    carpeta (las pruebas la usan para no tocar la configuración real).
  - Los textos estándar de Qt (Guardar, Cancelar, selector de color…) se muestran en español.

- **Buscar al soltar una conexión (como en Blender):** arrastra desde un socket y suéltalo en un
  espacio vacío. Se abre un buscador **filtrado a los nodos que tienen un socket compatible**,
  con la pista de a cuál se conectarán (`→ entrada Image`). Desde una **salida** se listan nodos
  con una entrada que la acepte; desde una **entrada**, nodos con una salida que pueda
  alimentarla. Primero van los de tipo idéntico, luego los que requieren una conversión
  implícita (p. ej. Integer → Float) y al final los genéricos (`Any`). Al elegir uno (clic, o
  escribir para filtrar y `Enter`) el nodo se crea **ya conectado**, con ese socket justo en el
  punto donde soltaste, en **un solo paso de deshacer**. `Esc` cancela. Soltar sobre un socket
  conecta directamente como antes, soltar sobre un nodo no hace nada, y arrastrar una conexión
  existente fuera de una entrada sigue eliminándola.

- **Parámetros conectables (escribir el valor o conectar otro nodo):** los parámetros enteros,
  decimales, booleanos, de color y de vector (35 en 15 nodos: Kernel, Sigma, Umbral, Bloque, C,
  Ángulo, Mínimo/Máximo de InRange, Grosor, Invertir…) tienen **su propio socket de entrada** a
  la izquierda de la fila, como en Blender.
  - **Sin conectar** se editan igual que antes (clic, texto o arrastre). **Conectado**, el campo se
    sustituye por la etiqueta y el valor viene del otro nodo; al desconectar vuelve el valor que
    tenía escrito (no se pierde).
  - El valor conectado pasa por las **mismas reglas que uno escrito**: conversión implícita de tipos
    (p. ej. `Float → Integer` redondea) y recorte al rango del parámetro (un `999` en un kernel de
    máximo 99 se queda en 99). Si el nodo de origen falla, el nodo alimentado queda bloqueado.
  - Funciona en todo: conectar con el ratón, el **buscador al soltar una conexión** (lista los nodos
    que pueden alimentar el parámetro, o los parámetros a los que se puede conectar una salida),
    proyectos, copiar/pegar, deshacer, tiempo real y la **exportación a Python** (el script calcula
    el valor conectado con la misma normalización que el motor).
  - No tienen socket los enumerados, textos y rutas, ni el propio valor de los nodos `Number`,
    `Integer`, `Boolean`, `Color`, `Vector2`, `Vector3`, ni los parámetros de las fuentes de
    video/cámara y `FPS` de Save Video.
  - Nuevos nodos de entrada **`Vector2`** y **`Vector3`** para alimentar los parámetros de vector.
  - Para que un nodo declare un parámetro sin socket: `ParamSpec(..., connectable=False)`.

- **Compilar a ejecutable** (**Archivo → Compilar a ejecutable…**, `Ctrl+Shift+E`): convierte el grafo
  en un programa que funciona **sin la aplicación ni Python** (solo en el sistema operativo donde se
  compila). Genera el mismo script que «Exportar Python» y lo compila con PyInstaller usando el Python
  de la aplicación; si PyInstaller no está instalado, pide permiso y lo instala con pip. Opciones:
  nombre, carpeta de salida, un solo archivo o carpeta, y mostrar u ocultar la consola. El avance se
  ve en el diálogo y los archivos temporales se borran al terminar.
  - Las rutas de importación de los nodos personalizados se pasan a PyInstaller (`--paths`) y los
    grafos con MediaPipe se compilan con `--collect-all mediapipe`.
  - Comprobado de verdad: un grafo sencillo (~60 MB, ~40 s) y uno con MediaPipe (~110 MB, ~75 s) se
    compilaron y se ejecutaron sin la aplicación (con los modelos en `PALANTIR_NODES_MODELS` o
    `~/.palantir_nodes/models`). Las rutas de archivos del grafo (imágenes, videos) son las de este
    equipo, igual que en el script exportado.
- **Conversiones** (categoría nueva): `Number to String` (con decimales), `String to Number` (acepta
  coma decimal; si no es un número usa un valor por defecto o muestra un error, a elección),
  `Integer to Float`, `Float to Integer` (piso, techo, redondeo o truncado) y los de color
  (`RGB to HSV`, `HSV to RGB`, `Convert Color Space`).
- **JSON:** `Value to JSON` (cualquier valor —número, vector, color, lista de puntos— a texto JSON,
  con decimales y modo compacto o con sangría) y `JSON Value` (saca un valor de un texto JSON con un
  camino de pasos separados por puntos, p. ej. `0.points.8.0`; si no existe, «Encontrado» es falso y no
  hay error). Con `String Viewer` se lee el JSON y con los nodos de red se envía.
- **`String Viewer`** (Salidas): recibe un texto y lo muestra dentro del nodo (recortado con «…» si es
  largo); al seleccionarlo o fijar el visor en él, el texto completo se lee —y se puede copiar— en el
  visor de resultados. El script exportado lo imprime cuando cambia.
- **Nodos nuevos:** `Sine` y `Cosine` (Matemáticas; radianes o grados), `Convert Color Space`
  (imagen entre BGR, RGB, HSV, HLS, Lab, YCrCb y gris), `RGB to HSV` y `HSV to RGB` (valores de
  color, con la escala de OpenCV: H 0-179, S y V 0-255, la misma de `Color Range`) y `Tick`.
- **Nodo `Tick`** (Entradas): avisa cada cierto tiempo. Salidas `Tick` (verdadero solo en el
  fotograma en que se cumple el intervalo), `Cuenta` y `Segundos`; parámetros intervalo y «Al
  iniciar». Es una fuente: con F5 mantiene el tiempo real activo aunque no haya cámara (como
  máximo a 60 fotogramas por segundo) y se exporta al script.
- **Librerías por proyecto** (menú **Nodos → Librerías del proyecto…**, `Ctrl+Shift+L`): cada
  proyecto activa las que necesita; sus nodos aparecen entonces en el menú de añadir y en el
  buscador, el proyecto guarda cuáles están activas y el script exportado importa y pide los
  paquetes necesarios en su encabezado. Desactivar una librería con nodos en el grafo pide
  confirmación y los elimina. El diálogo indica si falta algún paquete y trae el botón **Instalar paquetes que faltan**:
  pide confirmación mostrando el comando y ejecuta `pip install` con **el mismo Python que ejecuta la
  aplicación** (`sys.executable`), con el avance en pantalla; no se instala nada sin pulsarlo. Si
  instalas a mano, usa ese mismo Python (`.venv\Scripts\python -m pip install mediapipe`): un `pip`
  de otro entorno no lo verá la aplicación. Si un paquete está instalado pero falla al cargarse,
  el nodo muestra el error original y el comando exacto.
  - **Red (TCP)** (solo biblioteca estándar, sin instalar nada): `TCP Server` y `TCP Client` con las
    mismas entradas y salidas que los de WebSocket. TCP es un flujo de bytes, así que **cada línea
    es un mensaje**: lo que recibe se separa por saltos de línea y lo que envía termina en uno (los
    saltos que el propio texto contenga se envían como espacios). Sirve para Arduino/ESP32,
    scripts propios, `nc`, etc.
  - **MediaPipe** (se instala con el botón del diálogo; a mano:
    `pip install --no-deps mediapipe` y luego `pip install absl-py certifi flatbuffers matplotlib sounddevice`): `Hand
    Landmarks` (21 puntos por mano), `Pose Landmarks` (33 puntos del cuerpo), `Face Mesh` (478
    puntos) y `Face Detection` (cajas y 6 puntos clave). Cada uno dibuja sobre la imagen y entrega
    `Cantidad`, `Puntos` y `Cajas` (en píxeles); `Landmark Point` saca un punto concreto (p. ej.
    mano 0, índice 8 = punta del índice) como `Punto`, `X`, `Y` y `Encontrado`.
    - `Detections to JSON`: convierte `Puntos` y/o `Cajas` de un detector en texto JSON, una entrada por
      mano/persona/rostro: `[{"index":0,"box":[x,y,w,h],"points":[[x,y],...]}]`. «Solo puntos» limita a
      los índices indicados (p. ej. `4,8`) y «Decimales» redondea. Sirve para leerlo en un
      `String Viewer` o enviarlo por WebSocket/TCP, y `JSON Value` lo vuelve a abrir.
    - Se instala **sin dependencias** a propósito: `mediapipe` declara `opencv-contrib-python`, que
      reemplazaría el `cv2` que la aplicación ya tiene cargado, y Windows no deja sobrescribir
      `cv2.pyd` mientras está en uso (`Acceso denegado`, aunque seas administrador). No hace falta
      ejecutar nada como administrador: el entorno `.venv` es tuyo.
    - Usa la API «Tasks» de MediaPipe, que necesita un archivo de **modelo**. Si el campo «Modelo»
      está vacío se descarga el modelo oficial de Google la primera vez (necesita Internet) y se
      guarda en `~/.palantir_nodes/models` (o en la carpeta de la variable `PALANTIR_NODES_MODELS`);
      también puedes elegir tu propio archivo `.task`/`.tflite`.
    - El detector se crea una vez y se reutiliza en tiempo real; el script exportado hace lo mismo.
    - Comprobado con los modelos reales (los cuatro detectores arrancan y procesan imágenes); la
      detección de personas reales depende del modelo y no está cubierta por las pruebas, que usan
      un paquete falso.
  - **Red (WebSocket)** (requiere `pip install websockets`, o `pip install -e .[network]`):
    - `WebSocket Server`: abre un servidor (dirección y puerto) y entrega `Clientes` conectados,
      el último `Mensaje` recibido, `Mensaje nuevo` (verdadero solo en el fotograma en que llegó)
      y `Origen`. Usa `0.0.0.0` como dirección para aceptar otros equipos.
    - `WebSocket Client`: se conecta a un servidor que esté escuchando (reintenta cada segundo) y
      entrega `Conectado`, `Mensaje` y `Mensaje nuevo`.
    - Ambos envían texto a todos los conectados con las entradas `Mensaje` y `Enviar` (se envía en
      cada fotograma en que `Enviar` sea verdadero; conéctala a un `Tick` para enviar a intervalos).
    - El parámetro «Mensajes» decide qué pasa si llegan varios entre dos fotogramas: entregar solo
      el último o ir entregándolos en orden, uno por fotograma.
    - Son fuentes: el tiempo real (F5) abre y cierra las conexiones, y una ejecución automática
      no abre nada. Solo mueven texto; para números o JSON usa un nodo personalizado que lo
      interprete.
    - **Seguridad:** un servidor abierto en `0.0.0.0` acepta a cualquiera de tu red.
- **Chincheta para fijar el visor:** los nodos con imagen (los que la producen y los de salida)
  llevan una chincheta en la cabecera. Un clic deja el visor fijo en ese nodo aunque cambies la
  selección para editar otros; el título del visor añade «(fijado)». Otro clic la suelta (o fijar
  otro nodo la mueve) y se vuelve a seguir la selección. Se guarda en el proyecto; si el nodo se
  borra, se suelta sola.
- **Nodo `Slider`** (categoría Entrada): el valor se ajusta con un deslizador dentro del nodo
  (clic o arrastre; doble clic para escribirlo). En las propiedades se eligen el **mínimo**, el
  **máximo** y **Solo enteros**. Los extremos al revés se intercambian y el valor siempre queda
  dentro del rango. Su salida es de tipo `Float` (en modo entero toma valores enteros) y se puede
  conectar también a parámetros enteros.
- **Nodos personalizados en Python** (menú **Nodos**, `Ctrl+Shift+N`, también «Nuevo nodo
  personalizado…» en el menú de añadir y el botón en Preferencias). Se escribe una función y el
  programa la convierte en un nodo:
  - Se usa la **última función pública** del código (las que empiezan por `_` son auxiliares; puede
    haber `import`s y variables de módulo, que se ejecutan una sola vez).
  - **Parámetros → entradas** según su anotación: `int`, `float`, `bool`, `str`, `Image`
    (`np.ndarray`), `Color`, `Vector2`, `Vector3`, `Any`; `Literal["a", "b"]` crea una lista
    desplegable; un valor por defecto lo vuelve opcional, y `Image = None` es una entrada de imagen
    opcional. Sin anotación se infiere del valor por defecto.
  - **Retorno → salidas**: `-> Image`, `-> float`, `-> tuple[Image, int]`…; con varias salidas se
    nombran por las variables del `return` (si alguna no es un nombre simple: `result_1`, `result_2`…).
    Un `tuple[...]` en el retorno **siempre** son varias salidas; para una sola salida vectorial
    usa `-> Vector2`, `-> Vector3` o `-> Color`. Una función sin retorno es un nodo de salida (solo actúa
    al pulsar Ejecutar, nunca en la ejecución automática ni en tiempo real).
  - **Importar otras librerías:** el código puede hacer `import` de cualquier módulo de la biblioteca
    estándar o instalado en el Python de la aplicación. Para **módulos propios o librerías que tienes
    en otra carpeta del equipo**, el botón **Rutas de importación…** del gestor de nodos
    personalizados guarda las carpetas (en las preferencias) y las añade **al final** de `sys.path`
    (nunca tapan los paquetes de la aplicación); indica la carpeta que *contiene* el módulo. El panel
    de análisis avisa de los `import` que no se encuentran (sin ejecutarlos) y, si falla al ejecutar,
    el error sugiere esa opción. El script exportado repite las rutas con `sys.path.append(...)` (son
    rutas de este equipo) y lista en un comentario los paquetes importados.
  - Disponibles sin importar: `np`, `cv2`, `math`. Las imágenes de entrada son de **solo lectura**
    (usa `.copy()`); las de salida se normalizan a `uint8`. Los errores indican la línea del código
    del nodo.
  - El editor detecta entradas/salidas mientras se escribe, trae plantillas y resaltado de sintaxis,
    y permite crear, editar, duplicar y borrar. Si el grafo abierto usa el nodo, pide confirmación y
    adapta los nodos (conserva valores por nombre y quita las conexiones que dejaron de ser
    válidas; eso limpia el historial de deshacer).
  - Se guardan en `custom_nodes.json` de la carpeta de configuración; cada proyecto incluye las
    definiciones que usa y, al abrirlo en otro equipo, **pregunta** si importarlas.
  - Se exportan a Python: el código del nodo se define una vez en el script, con la misma
    normalización de salidas que el motor.
  - **Seguridad:** el código se ejecuta en el mismo proceso y con los permisos del usuario; abre
    proyectos de terceros solo si confías en ellos. El análisis nunca ejecuta el código.
  - Limitación: el código se incrusta con sangría, así que los textos multilínea de comillas
    triples no conservan su sangría original.

### Limitaciones conocidas

- **Tipo de socket `Video`:** Load Video y Webcam entregan un fotograma (`Image`) por
  iteración; el tipo `Video` como flujo completo no se usa todavía.
- **Webcam:** funciona en equipos reales, pero las pruebas automáticas la simulan (no hay cámara
  en el entorno de pruebas); la lectura de archivos de video sí está verificada de punta a punta.
- **Frames:** no se ajustan solos al tamaño de sus nodos ni se copian con copiar/pegar.
- **Nodos fuera de la especificación:** la biblioteca cubre todo lo que pedía la especificación;
  nodos adicionales (p. ej. operaciones aritméticas entre imágenes o conversión de espacio de
  color general) son ampliaciones opcionales.

Todas las acciones de la barra superior funcionan.

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
| Enmarcar selección en un frame | `Ctrl+J` |
| Encuadrar todo | `Inicio` |
| Cancelar conexión en curso | `Esc` o clic derecho |

### Comportamiento que comprueban las pruebas

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
10. Un frame agrupa y mueve sus nodos como un solo paso de deshacer, se redimensiona, se
    guarda y se reabre, y no cambia el resultado ni el script exportado.
11. Los valores se editan dentro del nodo (clic, texto, arrastre, menú, color, archivo) con
    deshacer, sin mover el nodo y sin disparar atajos mientras se escribe.
12. Cada nodo con imagen muestra su miniatura tras ejecutar y en tiempo real; se puede
    desactivar y no se calcula si está desactivada.
13. Las preferencias se guardan, se aplican al instante y un archivo dañado no impide arrancar.
14. Arrastrar un socket a un espacio vacío abre un buscador filtrado por compatibilidad y crea
    el nodo conectado en un solo paso de deshacer.
15. Cualquier parámetro numérico, booleano, de color o de vector se puede alimentar desde otro nodo,
    con el mismo resultado que escribir el valor, también en el script exportado.
16. `pytest` pasa (1056 pruebas: modelo, validación, motor, nodos, exportación, tiempo real,
    persistencia, frames, edición, previsualización, preferencias, nodos personalizados y UI real).
