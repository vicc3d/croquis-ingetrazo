# Iconos de IngeTrazo Croquis

Lista de trabajo para el rediseño del panel (bento). Criterio: **dibujar el
resultado, no la herramienta** (el mismo de tu propuesta del concurso):
cada icono muestra lo que ese ajuste le hace al dibujo.

## Tamaños y formato

| Uso | Tamaño | Dónde |
|---|---|---|
| Cabecera de caja | 16 px | El título de cada caja (Línea, Luz…) |
| Controles | 20 px | Botones segmentados y fichas |
| Icono de la extensión | 16, 24 y 256 px | Pestaña del panel, menú Extensiones y catálogo |

- Retícula de **24 px** para dibujar; se exporta a 20 y 16 px. Los de cabecera, revisados a 16 px.
- Trazo de **1,5 px** a 24 (1,25 a 20, 1 a 16), extremos redondeados.
- SVG de **un solo color** (`currentColor`), para que siga el tema claro u oscuro de IngeTrazo. Si alguno lleva acento, uno solo y pequeño.
- Nombre de archivo: el de la columna «Nombre» (`linea.svg`, `luz-sol.svg`…).

## Cabeceras de caja (16 px)

| # | Nombre | Caja | Metáfora |
|---|---|---|---|
| 1 | `estilo` | Estilo | Tres hojitas superpuestas, cada una con un relleno distinto (vacío, rayado, lleno): «elige un aspecto». |
| 2 | `linea` | Línea | Dos trazos a mano que se cruzan en una esquina y se pasan de largo. |
| 3 | `tecnica` | Técnica | Un trazo ancho de rotulador con la punta biselada al final. |
| 4 | `luz` | Luz | Un sol pequeño arriba a la izquierda y un cubo con la cara iluminada en blanco y la otra rellena. |
| 5 | `materiales` | Materiales | Dos muestras cuadradas superpuestas, una clara y una oscura. |
| 6 | `rayado` | Rayado en la sombra | Un cuadrado con líneas paralelas dentro, que no llegan del todo a los bordes. |
| 7 | `composicion` | Composición | Una hoja con un objeto al centro y el relleno que se deshace hacia los bordes. |
| 8 | `ajustes` | Ajustes finos | Tres deslizadores horizontales con sus perillas a distintas alturas. |

## Controles (20 px)

### Línea

| # | Nombre | Control | Metáfora |
|---|---|---|---|
| 9 | `contornos` | Contornos más gruesos | Un cubo con la silueta en trazo grueso y la arista interior fina. |
| 10 | `repasar` | Repasar líneas | Dos trazos casi paralelos, el segundo apenas corrido y más corto. |
| 11 | `cortes` | Cortar las líneas largas | Un trazo largo con un hueco pequeño, donde se levantó la pluma. |

### Técnica

| # | Nombre | Control | Metáfora |
|---|---|---|---|
| 12 | `rotulador` | Rotulador | Una franja ancha con dos o tres vetas y una línea más oscura donde se superponen dos pasadas. |
| 13 | `acuarela` | Acuarela | Una mancha de borde irregular con el borde más marcado, como cuando se seca el agua. |
| 14 | `solo-tinta` | Solo tinta | Un trazo fino a mano alzada, sin relleno. |

### Luz

| # | Nombre | Control | Metáfora |
|---|---|---|---|
| 15 | `luz-clasica` | Clásica | Una flecha que baja desde arriba a la izquierda sobre un cubo con la cara izquierda blanca. |
| 16 | `luz-sol` | El sol del modelo | Un sol con un reloj pequeño o un arco de su recorrido: el sol de una hora y un lugar. |
| 17 | `sombras` | Sombras arrojadas | Un cubo y su sombra rellena sobre el suelo. |

### Rayado

| # | Nombre | Control | Metáfora |
|---|---|---|---|
| 18 | `rayado-caras` | Paralelo a las caras | Un cubo con el rayado vertical en una cara y en la dirección del suelo en la otra. |
| 19 | `rayado-diagonal` | Diagonal | Un cuadrado con rayado a 45°. |
| 20 | `giro` | Giro del rayado | Tres líneas paralelas y una flecha curva que las rodea. |

### Composición

| # | Nombre | Control | Metáfora |
|---|---|---|---|
| 21 | `bordes-libres` | Bordes sin terminar | Un rectángulo con el relleno entero al centro que se deshace en trazos sueltos hacia afuera. |
| 22 | `construccion` | Líneas de construcción | Una esquina de la que salen dos líneas finas más allá del vértice. |
| 23 | `suelo` | Trazos de suelo | Tres o cuatro líneas en el suelo que convergen hacia un punto de fuga. |

### Acciones

| # | Nombre | Control | Metáfora |
|---|---|---|---|
| 24 | `dibujar` | Dibujar la vista (botón principal) | Un lápiz que termina un trazo sobre una hoja. |
| 25 | `guardar` | Guardar PNG (ventana del croquis) | Una hoja con una flecha hacia abajo. |
| 26 | `copiar` | Copiar (ventana del croquis) | Dos hojas superpuestas. |

## Icono de la extensión

| # | Nombre | Tamaños | Metáfora |
|---|---|---|---|
| 27 | `croquis` | 16, 24 y 256 px | Un cuaderno abierto con un cubo dibujado a mano, las líneas pasándose en las esquinas. Es el que aparece en la pestaña, en el menú Extensiones y en el catálogo. |

## Sin icono dibujado

- **Materiales** (Color, Grises, Contraste, Ninguno): van como muestras de color generadas por el programa, no como iconos.
- **Tamaño** (S, M, L): texto.
- **Miniaturas de los estilos** (Tinta, Rotulador gris, Rotulador color, Acuarela, Rayado, Contraste): propongo generarlas con el propio Croquis (un cubo pequeño dibujado con cada estilo), a 64 × 44 px y al doble para pantallas de alta densidad. Así muestran el resultado real y no hay que dibujarlas.
- El desplegable de **Ajustes finos** usa la flecha del sistema.
