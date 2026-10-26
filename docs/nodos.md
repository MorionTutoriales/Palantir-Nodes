# Catálogo de nodos

La aplicación incluye **61 nodos** en 6 categorías, más los de las [librerías opcionales](#librerías-opcionales). Esta página se genera con `tools/gen_nodes_doc.py` a partir del propio registro de nodos.

Los tipos de socket son: `Image`, `Float`, `Integer`, `Boolean`, `String`, `Color`, `Vector2`, `Vector3` y `Any`. Un decimal se puede conectar a un entero (se redondea), un entero o booleano a un decimal, y `Any` acepta cualquier valor. Los parámetros numéricos, booleanos, de color y de vector tienen además su propio socket de entrada para alimentarlos desde otro nodo.

## Entradas

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **Boolean** | Valor verdadero o falso. | — | `Value` (Boolean) | Valor |
| **Color** | Color RGB. | — | `Color` (Color) | Color |
| **Integer** | Valor numérico entero. | — | `Value` (Integer) | Valor |
| **Load Image** | Carga una imagen desde disco. | — | `Image` (Image), `Width` (Integer), `Height` (Integer) | Archivo, Modo |
| **Load Video** | Fuente de fotogramas desde un archivo de video. En tiempo real entrega un fotograma por iteración; en modo estático muestra el primero. | — | `Fotograma` (Image) | Archivo, Repetir |
| **Number** | Valor numérico decimal. | — | `Value` (Float) | Valor |
| **Slider** | Valor numérico que se ajusta con un deslizador dentro del nodo. El mínimo, el máximo y si son solo enteros se eligen en las propiedades. | — | `Value` (Float) | Valor, Mínimo, Máximo, Solo enteros |
| **Tick** | Avisa cada cierto tiempo: «Tick» es verdadero solo en el fotograma en que se cumple el intervalo. Funciona en tiempo real (F5) y lo mantiene activo aunque no haya cámara; con un Tick el tiempo real va como máximo a 60 fotogramas por segundo. | — | `Tick` (Boolean), `Cuenta` (Integer), `Segundos` (Float) | Intervalo (s), Al iniciar |
| **Vector2** | Vector de dos componentes. | — | `Vector` (Vector2) | Valor |
| **Vector3** | Vector de tres componentes. | — | `Vector` (Vector3) | Valor |
| **Webcam** | Fotogramas de una cámara. Solo funciona en tiempo real (Ejecutar, F5). | — | `Fotograma` (Image) | Cámara |

## Imagen

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **Adaptive Threshold** | Umbral adaptativo por vecindad. | `Image` (Image) | `Image` (Image) | Valor máx., Método, Tipo, Bloque, C |
| **Canny Edge Detection** | Detección de bordes de Canny. | `Image` (Image) | `Edges` (Image) | Umbral 1, Umbral 2, Apertura, Gradiente L2 |
| **Color Range (InRange)** | Máscara de los píxeles dentro de un rango de color. | `Image` (Image) | `Máscara` (Image) | Convertir a HSV, Mínimo, Máximo |
| **Crop** | Recorta una región rectangular. | `Image` (Image) | `Image` (Image) | X, Y, Ancho, Alto |
| **Dilate** | Dilatación morfológica. | `Image` (Image) | `Image` (Image) | Kernel, Forma, Iteraciones |
| **Draw Contours** | Dibuja contornos sobre una imagen. | `Image` (Image), `Contornos` (Any) | `Image` (Image) | Color, Grosor, Índice |
| **Erode** | Erosión morfológica. | `Image` (Image) | `Image` (Image) | Kernel, Forma, Iteraciones |
| **Find Contours** | Encuentra contornos en una imagen binaria (todo lo distinto de 0 cuenta). | `Image` (Image) | `Contornos` (Any), `Cantidad` (Integer) | Modo, Aproximación |
| **Flip** | Voltea la imagen. | `Image` (Image) | `Image` (Image) | Eje |
| **Gaussian Blur** | Desenfoque gaussiano. | `Image` (Image) | `Image` (Image) | Kernel, Sigma |
| **Grayscale** | Convierte la imagen a escala de grises. | `Image` (Image) | `Image` (Image) | — |
| **HSV Conversion** | Convierte entre BGR y HSV (H: 0-179, S y V: 0-255). | `Image` (Image) | `Image` (Image) | Dirección |
| **Median Blur** | Filtro de mediana (elimina ruido sal y pimienta). | `Image` (Image) | `Image` (Image) | Kernel |
| **Morphological Operations** | Apertura, cierre, gradiente, top hat y black hat. | `Image` (Image) | `Image` (Image) | Operación, Kernel, Forma, Iteraciones |
| **Resize** | Cambia el tamaño de la imagen por escala o a dimensiones fijas. | `Image` (Image) | `Image` (Image) | Modo, Escala, Ancho, Alto, Interpolación |
| **Rotate** | Rota la imagen alrededor de su centro (positivo = antihorario). | `Image` (Image) | `Image` (Image) | Ángulo, Ampliar lienzo, Interpolación |
| **Threshold** | Umbral global (convierte a gris si hace falta). | `Image` (Image) | `Image` (Image), `Umbral usado` (Float) | Umbral, Valor máx., Método, Otsu |

## Matemáticas

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **Add** | A + B | `A` (Float), `B` (Float) | `Resultado` (Float) | — |
| **Clamp** | Limita un valor al rango [mín, máx]. | `Valor` (Float), `Mín` (Float), `Máx` (Float) | `Resultado` (Float) | — |
| **Compare** | Compara A con B. | `A` (Float), `B` (Float) | `Resultado` (Boolean) | Operación |
| **Cosine** | Coseno del ángulo (resultado entre -1 y 1). | `Ángulo` (Float) | `Resultado` (Float) | Unidad |
| **Divide** | A ÷ B | `A` (Float), `B` (Float) | `Resultado` (Float) | — |
| **Map Range** | Reasigna un valor de un rango a otro. | `Valor` (Float), `Desde mín` (Float), `Desde máx` (Float), `Hacia mín` (Float), `Hacia máx` (Float) | `Resultado` (Float) | Limitar al rango |
| **Maximum** | El mayor de A y B. | `A` (Float), `B` (Float) | `Resultado` (Float) | — |
| **Minimum** | El menor de A y B. | `A` (Float), `B` (Float) | `Resultado` (Float) | — |
| **Multiply** | A × B | `A` (Float), `B` (Float) | `Resultado` (Float) | — |
| **Sine** | Seno del ángulo (resultado entre -1 y 1). | `Ángulo` (Float) | `Resultado` (Float) | Unidad |
| **Subtract** | A − B | `A` (Float), `B` (Float) | `Resultado` (Float) | — |

## Conversión

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **Convert Color Space** | Convierte una imagen entre BGR, RGB, HSV, HLS, Lab, YCrCb y gris. En HSV: H 0-179, S y V 0-255. Indica en qué espacio está la imagen de entrada (origen). | `Image` (Image) | `Image` (Image) | Origen, Destino |
| **Float to Integer** | Convierte un decimal en entero: piso, techo, redondeo o truncado. | `Decimal` (Float) | `Entero` (Integer) | Modo |
| **HSV to RGB** | Convierte un HSV de OpenCV (H 0-179, S y V 0-255) en un color RGB. | `HSV` (Vector3) | `Color` (Color) | — |
| **Integer to Float** | Convierte un entero en un número decimal. | `Entero` (Integer) | `Decimal` (Float) | — |
| **JSON Value** | Saca un valor de un texto JSON siguiendo un camino de pasos separados por puntos (posición en listas o nombre de clave), p. ej. «0.points.8.0». Si no existe o el texto no es JSON, «Encontrado» es falso. | `JSON` (String) | `Número` (Float), `Texto` (String), `Encontrado` (Boolean) | Camino |
| **Number to String** | Convierte un número en texto con los decimales indicados. | `Número` (Float) | `Texto` (String) | Decimales |
| **RGB to HSV** | Convierte un color RGB en HSV de OpenCV (H 0-179, S y V 0-255). | `Color` (Color) | `HSV` (Vector3) | — |
| **String to Number** | Convierte un texto en número (acepta coma decimal). Si no es un número, falla o usa el valor por defecto, según «Si no es válido». | `Texto` (String) | `Número` (Float), `Válido` (Boolean) | Si no es válido, Por defecto |
| **Value to JSON** | Convierte un valor (número, vector, color, lista de puntos…) en texto JSON, listo para mostrarlo en un String Viewer o enviarlo por la red. | `Valor` (Any) | `JSON` (String) | Decimales, Compacto |

## Composición

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **Add Weighted** | A·alfa + B·beta + gamma. | `Imagen A` (Image), `Imagen B` (Image), `Alfa` (Float), `Beta` (Float), `Gamma` (Float) | `Image` (Image) | — |
| **Bitwise AND** | AND bit a bit entre dos imágenes. | `Imagen A` (Image), `Imagen B` (Image) | `Image` (Image) | — |
| **Bitwise NOT** | Invierte los bits de la imagen. | `Image` (Image) | `Image` (Image) | — |
| **Bitwise OR** | OR bit a bit entre dos imágenes. | `Imagen A` (Image), `Imagen B` (Image) | `Image` (Image) | — |
| **Blend Images** | Mezcla dos imágenes (B se ajusta al tamaño de A). | `Factor` (Float), `Imagen A` (Image), `Imagen B` (Image) | `Image` (Image) | Modo |
| **Mask** | Conserva los píxeles donde la máscara es distinta de 0. | `Image` (Image), `Máscara` (Image) | `Image` (Image) | Invertir máscara |
| **Merge Channels** | Combina tres canales en una imagen BGR. | `Azul` (Image), `Verde` (Image), `Rojo` (Image) | `Image` (Image) | — |
| **Split Channels** | Separa una imagen en sus canales B, G y R. | `Image` (Image) | `Azul` (Image), `Verde` (Image), `Rojo` (Image) | — |

## Salidas

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **Image Viewer** | Muestra la imagen en el visor de resultados. | `Image` (Image) | — | — |
| **Save Image** | Guarda la imagen en disco al pulsar Ejecutar (no en la ejecución automática). | `Image` (Image) | — | Archivo |
| **Save Video** | Escribe los fotogramas en un archivo de video (solo en tiempo real con F5). | `Fotograma` (Image) | — | Archivo, FPS, Códec |
| **String Viewer** | Muestra un texto dentro del nodo. Al seleccionarlo (o fijar el visor en él) el texto completo se lee en el visor de resultados; el script exportado lo imprime en la consola. | `Texto` (String) | — | — |
| **Video Viewer** | Muestra los fotogramas en el visor (con FPS) durante la ejecución en tiempo real. | `Fotograma` (Image) | — | — |

## Librerías opcionales

Se activan por proyecto en **Nodos → Librerías del proyecto…** y sus nodos aparecen entonces en el menú de añadir.

### Red (WebSocket)

Comunicación en tiempo real por WebSocket. «WebSocket Server» abre un servidor, recibe lo que le envían los clientes y puede enviarles datos; «WebSocket Client» se conecta a un servidor que esté escuchando. Funcionan en tiempo real (F5) y cada nodo mantiene el tiempo real activo mientras esté en el grafo.

Necesita: `websockets`.

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **WebSocket Server** | Abre un servidor WebSocket y recibe lo que le envíen los clientes. Con «Enviar» y «Mensaje» conectados, manda ese texto a todos los clientes. Usa 0.0.0.0 como dirección para aceptar conexiones desde otros equipos. | `Enviar` (Boolean), `Mensaje` (String) | `Clientes` (Integer), `Mensaje` (String), `Mensaje nuevo` (Boolean), `Origen` (String) | Dirección, Puerto, Mensajes |
| **WebSocket Client** | Se conecta a un servidor WebSocket que esté escuchando (reintenta cada segundo si no está o se cae). Recibe sus mensajes y puede enviarle texto con «Enviar» y «Mensaje». | `Enviar` (Boolean), `Mensaje` (String) | `Conectado` (Boolean), `Mensaje` (String), `Mensaje nuevo` (Boolean) | Dirección, Mensajes |

### Red (TCP)

Comunicación por sockets TCP sin paquetes adicionales. «TCP Server» abre un servidor, recibe lo que le envían los clientes y puede enviarles datos; «TCP Client» se conecta a un servidor que esté escuchando. Cada línea (terminada en salto de línea) es un mensaje. Funcionan en tiempo real (F5), como los nodos WebSocket.

Necesita: nada (solo Python).

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **TCP Server** | Abre un servidor TCP y recibe lo que le envíen los clientes: cada línea es un mensaje. Con «Enviar» y «Mensaje» conectados, manda ese texto (terminado en salto de línea) a todos los clientes. Usa 0.0.0.0 como dirección para aceptar conexiones de otros equipos. | `Enviar` (Boolean), `Mensaje` (String) | `Clientes` (Integer), `Mensaje` (String), `Mensaje nuevo` (Boolean), `Origen` (String) | Dirección, Puerto, Mensajes |
| **TCP Client** | Se conecta a un servidor TCP que esté escuchando (reintenta cada segundo si no está o se cae). Cada línea que recibe es un mensaje; puede enviarle texto con «Enviar» y «Mensaje». | `Enviar` (Boolean), `Mensaje` (String) | `Conectado` (Boolean), `Mensaje` (String), `Mensaje nuevo` (Boolean) | Dirección, Puerto, Mensajes |

### MediaPipe

Detección de manos, cuerpo y rostros con MediaPipe. Cada detector dibuja los puntos sobre la imagen y entrega su cantidad, los puntos y las cajas; «Landmark Point» saca un punto concreto (p. ej. la punta del índice) como coordenadas. La primera vez cada detector descarga su modelo oficial (necesita Internet) y lo guarda en ~/.palantir_nodes/models; también puedes indicar tu propio archivo de modelo.

Necesita: `mediapipe`, `absl-py`, `certifi`, `flatbuffers`, `matplotlib`, `sounddevice`.

| Nodo | Qué hace | Entradas | Salidas | Parámetros |
|---|---|---|---|---|
| **Hand Landmarks** | Detecta manos y sus 21 puntos (punta del índice = 8, del pulgar = 4). «Puntos» da, por cada mano, la lista de puntos en píxeles; úsala con «Landmark Point». | `Image` (Image) | `Imagen` (Image), `Cantidad` (Integer), `Puntos` (Any), `Cajas` (Any) | Manos, Confianza mínima, Dibujar, Modelo |
| **Pose Landmarks** | Detecta el cuerpo y sus 33 puntos (0 = nariz, 11/12 = hombros, 15/16 = muñecas, 27/28 = tobillos). «Puntos» da, por cada persona, la lista de puntos en píxeles. | `Image` (Image) | `Imagen` (Image), `Cantidad` (Integer), `Puntos` (Any), `Cajas` (Any) | Personas, Confianza mínima, Dibujar, Modelo |
| **Face Mesh** | Detecta rostros y su malla de 478 puntos. «Puntos» da, por cada rostro, la lista de puntos en píxeles. | `Image` (Image) | `Imagen` (Image), `Cantidad` (Integer), `Puntos` (Any), `Cajas` (Any) | Rostros, Confianza mínima, Dibujar, Modelo |
| **Face Detection** | Detecta rostros: «Cajas» da (x, y, ancho, alto) de cada uno y «Puntos» sus 6 puntos clave (ojos, nariz, boca y orejas). Es más rápido que Face Mesh. | `Image` (Image) | `Imagen` (Image), `Cantidad` (Integer), `Puntos` (Any), `Cajas` (Any) | Confianza mínima, Dibujar, Modelo |
| **Landmark Point** | Toma un punto de la salida «Puntos» de un detector: «Elemento» es cuál mano, persona o rostro (0 = el primero) e «Índice» cuál punto. Da sus coordenadas en píxeles y si existe. | `Puntos` (Any) | `Punto` (Vector2), `X` (Float), `Y` (Float), `Encontrado` (Boolean) | Elemento, Índice |
| **Detections to JSON** | Convierte los «Puntos» y/o las «Cajas» de un detector en texto JSON: una entrada por mano, persona o rostro con su posición, su caja y sus puntos en píxeles. Sirve para leerlo en un String Viewer o enviarlo por la red; con «JSON Value» se vuelve a abrir. | `Puntos` (Any), `Cajas` (Any) | `JSON` (String) | Solo puntos, Decimales, Compacto |
