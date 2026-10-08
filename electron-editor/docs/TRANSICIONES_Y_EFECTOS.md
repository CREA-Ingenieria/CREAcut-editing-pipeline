# Transiciones y efectos en CREAcut Beta

## 1. Qué se ve ahora en la aplicación

| Elemento | Dónde se ve | Cómo está resuelto |
|---|---|---|
| Filtros con duración | Los tres modos del reproductor | `filter` CSS sobre el `<video>` |
| Transición entre cortes | Modo **Previsualización**, reproduciendo | Fotograma congelado + capa animada |
| Chroma, fondo, piel | Botón «Previsualizar fotograma actual» | Render de un fotograma en Python |

Los filtros ya funcionaban: `VideoPreview` aplica `visualEffectCss()` al elemento
`<video>`, y `sourceTimeS` es siempre el `currentTime` real, así que el filtro
acompaña al material en los tres modos. Lo nuevo son las transiciones.

## 2. Cómo se previsualiza una transición

El render real funde dos clips: durante la transición los dos avanzan a la vez.
En la previsualización solo hay **un** elemento `<video>`, y un `<video>` no
puede reproducir dos tramos del mismo archivo simultáneamente.

La aproximación: congelar el último fotograma del corte saliente y animar esa
imagen fija sobre el corte entrante, que sí sigue reproduciéndose.

```text
  … clip saliente ──┐                      ┌── clip entrante …
                    │        corte         │
   captura ─────────┤◄── 0.35 s ──►│       │
                                   │◄── crossfadeS ──►│
                                   └─ se retira la capa congelada
```

El ciclo, por cada corte:

1. el cabezal entra en la ventana previa al corte y el clip saliente todavía
   está en pantalla → se vuelca ese fotograma a un `<canvas>`;
2. el reproductor salta al clip siguiente al llegar al corte;
3. mientras dura la transición, la capa del canvas se retira encima del clip
   entrante siguiendo el estilo configurado.

### Por qué se captura antes del corte y no en el corte

En el instante exacto del corte el `<video>` **ya muestra el clip entrante**:
capturar ahí congelaría la imagen equivocada. La ventana previa es el único
momento en que el fotograma saliente sigue en pantalla.

Esa ventana es de 0.35 s y el valor no es arbitrario: tiene que ser mayor que el
intervalo entre eventos `timeupdate`, que Chromium emite cada 60–250 ms. Con una
ventana más corta, un corte podría cruzarse sin que ninguna lectura del reloj
cayera dentro y la transición se quedaría sin imagen que animar.

### Los cinco estilos salen de la misma capa

No hay un mecanismo por estilo; hay una capa y cuatro formas de retirarla:

| Estilo | Cómo se retira la capa congelada | ¿Se mueve el entrante? |
|---|---|---|
| `dissolve` | La opacidad baja de 1 a 0. | No |
| `fade_black` | Primera mitad funde a negro, segunda abre desde negro. | No |
| `wipe_left` | `clip-path: inset()` crece por el borde derecho. | No |
| `slide_left` | `translateX` la desplaza fuera de cuadro. | **Sí** |
| `cut` | No se crea ninguna transición. | — |

### El deslizamiento mueve los dos clips

`slide_left` es el único estilo en el que el clip entrante también se desplaza,
y por eso el `<video>` recibe su propio `transform`. Si solo se moviera la capa
congelada, el entrante se quedaría quieto en el centro y se verían las dos
imágenes a la vez, como si el video estuviera duplicado.

El desplazamiento va en **píxeles del ancho visible**, no en porcentaje del
elemento. El `<video>` usa `object-contain`, así que su contenido casi nunca
llena el elemento: quedan franjas negras a los lados. Desplazar un 100 % del
elemento movería cada clip más que su propio ancho y dejaría un hueco negro
entre los dos justo en mitad del movimiento. Midiendo el rectángulo real
(`videoFrameRect`) los dos clips quedan pegados borde con borde.

Ese mismo rectángulo es el que posiciona la capa congelada: a pantalla completa
quedaría desalineada respecto a lo que se ve, y el recorte del barrido cortaría
por el sitio equivocado.

### Qué diferencia hay con el render final

La capa saliente está **congelada**; en el render sigue en movimiento. Se nota
solo si hay mucho movimiento en el clip saliente y solo mientras dura la
transición. A cambio no hace falta un segundo decodificador ni pedirle nada al
backend: los puntos de corte (`preview.cutPointsS`) ya venían en el contrato.

La previsualización tampoco se activa al arrastrar el cabezal, solo
reproduciendo: buscando un instante, una capa animada encima solo estorbaría.

## 3. Archivos

```text
src/renderer/src/
├── services/transition-preview.ts     # Reglas puras: cuándo y con qué geometría
├── hooks/useTransitionPreview.ts      # Captura del fotograma y transición activa
├── components/TransitionOverlay.tsx   # Las dos capas sobre el video
└── components/VideoPreview.tsx        # Monta el overlay
```

El reparto es el mismo del resto del editor: la regla vive en `services` sin
tocar React ni el DOM, lo imperativo (hablar con el `<video>` y el `<canvas>`)
vive en el hook, y el componente solo pinta.

El `<canvas>` está **siempre montado**, aunque no haya transición: es donde se
vuelca el fotograma antes de que el corte ocurra, así que desmontarlo entre
transiciones destruiría justo la imagen que hace falta un instante después. Lo
que cambia es su opacidad.

## 4. El tope de duración lo pone el backend

`bridge.py` rechaza con un error cualquier `crossfadeS` fuera de **0–0.5 s**
(`_validated_render_setting`). El deslizador de la interfaz termina exactamente
en ese tope: si permitiera más, el usuario podría elegir un valor que la
aplicación no puede guardar y solo se enteraría al ver el error.

Si algún día ese límite cambia en Python, hay que actualizar también el máximo
del control correspondiente en `components/inspector/ProjectInspector.tsx`.

## 5. Alcance actual

La transición es **del proyecto entero**: un estilo y una duración para todos
los cortes, tal como los guarda `ProjectRenderSettings`. No existe todavía la
transición por corte; eso exige añadir campos al esquema de `EditProject` en
Python, y `from_dict` rechaza cualquier `schema_version` distinta a la suya sin
ruta de migración, así que los proyectos ya guardados dejarían de abrir. Es una
etapa aparte que empieza por escribir esa migración.

## 6. Cómo probarlo a mano

1. Abre un proyecto con al menos dos cortes y ve a la pestaña
   **Previsualización**.
2. En el inspector del proyecto, elige un estilo distinto de «Corte directo» y
   sube la duración al tope (0.50 s) para verla con holgura.
3. Pulsa reproducir y deja que el cabezal cruce un corte.
4. Repite cambiando el estilo: disolvencia, fundido a negro, barrido y
   deslizamiento deben verse claramente distintos.
5. Pon el estilo en «Corte directo»: el deslizador de duración debe quedar
   deshabilitado y no debe aparecer ninguna capa.
6. Arrastra el cabezal por encima de un corte sin reproducir: no debe aparecer
   ninguna transición.
7. Baja la duración a 0 con un estilo activo: tampoco debe aparecer nada.
8. Con «Deslizamiento lateral», comprueba que los dos clips viajan pegados: no
   debe verse la imagen duplicada ni una franja negra entre ellos.
9. Cambia el tamaño de la ventana durante la reproducción: la capa congelada
   debe seguir encajando con el video.
