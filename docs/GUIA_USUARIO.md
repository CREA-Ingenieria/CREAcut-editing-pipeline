# Guía de usuario de CREAcut Beta

> Esta guía corresponde a la beta `0.2.0-beta.1`. La aplicación todavía no ha
> sido probada por completo; conserva copias de tus archivos importantes.

## 1. La idea del proyecto

CREAcut reduce el trabajo repetitivo de editar una clase grabada. Transcribe el
audio, compara lo dicho con el guion, detecta posibles retomas y construye una
propuesta. La propuesta se guarda como un proyecto editable para que una persona
pueda revisarla antes de generar el video final.

| Archivo | Qué es | Cuándo se crea |
|---|---|---|
| Video fuente | La grabación original, por ejemplo `clase.mp4`. | Antes de CREAcut. |
| Proyecto | Las decisiones editables, `clase.creacut.json`. | Después del análisis. |
| Video final | El MP4 renderizado y aprobado. | Después de revisar y exportar. |

El proyecto no contiene el video completo. Guarda una referencia al archivo
fuente, la transcripción, el guion, las tomas candidatas y las decisiones.

## 2. Pantalla inicial

La pantalla inicial permite crear un proyecto, abrir uno existente, procesar un
lote, abrir proyectos recientes, recuperar cambios y comprobar el backend.

### Nuevo proyecto

| Campo | Obligatorio | Explicación |
|---|---|---|
| Video fuente | Sí | Grabación que se transcribirá. |
| Guion Markdown | Sí | Texto esperado para alinear las tomas. |
| Proyecto de salida | Sí | Ruta del nuevo `.creacut.json`; no es el MP4. |
| Configuración YAML | No | Ajustes de Whisper, chroma, overlays y render. |
| Fondo para chroma | No | Imagen que reemplaza el fondo verde. |

Al iniciar, CREAcut ejecuta Whisper y la alineación. El diálogo muestra el
progreso y el dispositivo: CUDA/FP16 cuando está disponible o CPU/FP32 cuando
no lo está.

### Procesar lote

El lote recibe todos los videos y la misma cantidad de guiones. No se crean
parejas manualmente. Para cada video:

1. Whisper genera o reutiliza la transcripción.
2. El pipeline compara los primeros segundos con los guiones disponibles.
3. Selecciona el mejor guion y muestra un porcentaje.
4. Retira ese guion para mantener una relación uno a uno.
5. Copia video y guion a una carpeta independiente.
6. Genera el proyecto editable.

Una coincidencia baja debe revisarse. El algoritmo ayuda a organizar el lote,
pero no sustituye la verificación humana cuando los guiones comienzan igual.

## 3. Pantalla de edición

La pantalla está dividida en cabecera, recursos (transcripción y guion), visor,
timeline e inspector. Los paneles laterales y el timeline se pueden plegar o
redimensionar.

### Video original y edición propuesta

**Video original** reproduce el archivo completo. **Edición propuesta** usa el
mismo archivo, pero salta los rangos descartados. No genera un proxy ni un MP4
temporal.

Los botones anterior y siguiente navegan al inicio del clip editado anterior o
siguiente. Si no existe otro clip, no envían el cabezal al final del video.

### Transcripción, guion y tomas

Al seleccionar una parte de la transcripción o del guion, el reproductor salta
al rango correspondiente. El inspector muestra texto, tiempo, puntaje, toma
recomendada y alternativas. **Usar esta toma** modifica el proyecto, nunca el
MP4 fuente. **Restaurar** vuelve a la recomendación automática.

Durante la reproducción, CREAcut resalta simultáneamente el fragmento activo de
la transcripción y su oración correspondiente en el guion. Ambas listas se
desplazan para mantener visible el elemento activo.

### Timeline

El timeline siempre usa el reloj del video fuente. Permite mover el playhead,
conservar, descartar, restaurar, dividir, mover bordes, hacer zoom y deshacer o
rehacer. Al seleccionar una parte de la transcripción o del guion, la línea de
tiempo se desplaza horizontalmente para mostrar la nueva posición del playhead
amarillo. Sus pistas separan video, audio, efectos, cortes y diapositivas. Las
miniaturas y el waveform son cachés visuales; no alteran el video.

## 4. Guardar y recuperar

`Ctrl+S` guarda el proyecto. `Ctrl+Shift+S` permite elegir otra ruta. Antes de
cerrar con cambios pendientes, CREAcut ofrece guardar, descartar o cancelar.

Electron mantiene una recuperación mientras hay cambios. Si el proceso termina
inesperadamente, Python valida esa copia antes de restaurarla. Una recuperación
incompatible se rechaza sin modificar el `.creacut.json` original.

## 5. Exportar MP4

Al exportar, CREAcut guarda el proyecto, compila los rangos aprobados y aplica
cortes, chroma, overlays, bookends y normalización. No repite Whisper ni la
alineación.

## 6. Preview frente a render

| Función | Preview | Render final |
|---|---:|---:|
| Saltos entre rangos | Sí | Sí |
| Cambio de tomas | Sí | Sí |
| Filtros temporales | Sí, aproximación CSS | Sí |
| Chroma, fondo y piel | Fotograma solicitado | Sí |
| Diapositiva y presentador | Fotograma solicitado | Sí |
| Overlays de texto | No | Sí |
| Transiciones | Sí, aproximadas | Sí |
| Intro y cierre | No | Sí |
| Normalización EBU R128 | No | Sí |

## 7. Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+O` | Abrir proyecto. |
| `Ctrl+S` | Guardar. |
| `Ctrl+Shift+S` | Guardar como. |
| `Ctrl+E` | Exportar MP4. |
| `Ctrl+Z` | Deshacer. |
| `Ctrl+Shift+Z` | Rehacer. |
| Espacio | Reproducir o pausar. |

En macOS, la interfaz mantiene actualmente estos atajos con `Ctrl`; todavía no
existe un mapeo adicional a `Command`.

## 8. Archivos auxiliares

| Elemento | Propósito | Se puede regenerar |
|---|---|---:|
| `.whisper.json` | Caché de transcripción. | Sí. |
| `.creacut-cache/` | Miniaturas y waveform. | Sí. |
| `.creacut.json` | Proyecto y decisiones. | No debe borrarse sin respaldo. |
| `.creacut-assets/` | Diapositivas, imágenes y miniaturas importadas. | Solo desde los originales. |
| MP4 final | Resultado exportado. | Sí, desde el proyecto. |

## 9. Problemas frecuentes

- **Backend desconectado en desarrollo:** verifica la `.venv` indicada por
  `CREACUT_PYTHON`. En una app instalada, comprueba que el antivirus o
  Gatekeeper no haya bloqueado `uv` o el entorno preparado.
- **Video movido:** usa **Ubicar video** y selecciona el archivo correcto.
- **Sin audio o seek incorrecto:** prueba un MP4 H.264/AAC compatible con
  Chromium.
- **Resultado diferente al preview:** revisa la tabla de efectos finales.
- **Whisper en CPU:** en Windows valida CUDA en la misma `.venv`; en macOS el
  selector actual todavía no activa MPS.

## 10. Qué interfaz debo usar

Usa Electron para el flujo actual. PySide6 se conserva para compatibilidad y
diagnóstico, pero las mejoras nuevas se realizan primero en Electron.

## 11. Estado actual y limitaciones

| Área | Estado | Qué significa |
|---|---|---|
| Crear y abrir proyectos editables | Operativo | Electron solicita el análisis al backend y carga archivos `.creacut.json`. |
| Reproducir, navegar y revisar cortes | Operativo | Se puede trabajar desde el video, el timeline, el guion, la transcripción y las tomas. |
| Conservar, descartar, restaurar y dividir | Operativo | Las decisiones quedan guardadas antes del render final. |
| Recuperación de proyecto | Operativo con validación | El backend comprueba la procedencia e integridad antes de restaurar. |
| Exportación MP4 | Operativo | Parte del proyecto aprobado y no repite Whisper ni la alineación. |
| Procesamiento por lote | Operativo | Recibe videos y guiones por separado y el pipeline busca sus correspondencias. |
| Whisper con NVIDIA CUDA | Dependiente del equipo | Requiere PyTorch compatible y CUDA disponible; no se sustituye silenciosamente por CPU. |
| Whisper en macOS | Operativo por CPU | La selección automática actual todavía no utiliza Metal/MPS. |
| Diapositivas y presentador | Beta | Importa, propone tiempos, permite ajustar y renderiza; requiere revisión manual. |
| Instalador de Windows | Configurado | Genera NSIS x64; prepara el backend Python y FFmpeg al instalar. |
| Instalador de macOS | Configurado, pendiente de validación en Mac | DMG arm64 con fuentes y `uv`; prepara el entorno en el primer arranque. |
| Firma y notarización | No configurado | SmartScreen o Gatekeeper pueden advertir sobre paquetes sin firma. |
| Backend autónomo | Implementado en empaquetado | Windows construye el entorno con Python, el Core y FFmpeg desde PyPI al instalar, y prepara Whisper y Gemma 4; macOS hace lo mismo en el primer arranque, con una pantalla de preparación. |

La pestaña **Previsualización** prioriza una revisión rápida del montaje y sus
cortes. El inspector también puede generar un fotograma exacto con chroma,
fondo y corrección de piel. Overlays, transiciones animadas, bookends y
normalización se comprueban en el MP4 final. Los estados “configurado” tampoco significan
“validado en todos los equipos”: FFmpeg, CUDA, modelos e instaladores dependen
del sistema donde se construyan o ejecuten.

## 12. Inspector del proyecto y de la selección

El panel derecho separa la configuración general de las propiedades del
elemento seleccionado:

- **Proyecto:** transición, chroma, fondo, corrección de piel, filtros,
  elementos gráficos y normalización de audio.
- **Diapositivas:** importación, análisis, propuestas y biblioteca.
- **Selección contextual:** propiedades de la región, filtro, diapositiva o toma
  seleccionada en el editor.

Las transiciones disponibles son **corte directo**, **disolvencia**, **fundido
a negro**, **barrido lateral** y **deslizamiento lateral**. En las transiciones
animadas, el pipeline solapa imagen y audio usando la duración elegida; el corte
directo no crea solapamiento.

El botón **Previsualizar fotograma actual** pausa la reproducción y reemplaza
temporalmente el visor central por una imagen procesada en el instante del
playhead. Esta imagen pasa por los mismos motores Python de chroma, fondo y
corrección de piel que el render. Pulsa la **X** del visor para regresar al
video. Las transiciones necesitan dos tomas, y los gráficos y el audio necesitan
tiempo; por eso se verifican exportando un MP4 corto.

### Filtros temporales y pista arrastrable

Los filtros **Cinematográfico**, **Cálido**, **Frío**, **Blanco y negro**,
**Vintage** y **Colores vivos** sí se previsualizan durante todo el video:

1. Coloca el playhead amarillo donde debe comenzar el filtro.
2. Selecciona el filtro y pulsa **Agregar**. Se crea un bloque inicial de cinco
   segundos en la pista **EFECTOS**.
3. Arrastra el centro del bloque para moverlo completo.
4. Arrastra el extremo izquierdo para cambiar el inicio o el derecho para
   cambiar el final.
5. Pulsa Play. El filtro se activa al entrar al bloque y se desactiva al salir.

El bloque seleccionado también aparece en el inspector, donde se puede cambiar
su tipo o eliminarlo. Sus tiempos usan el video fuente, se guardan en el
`.creacut.json` y Python vuelve a aplicarlos al exportar. Dos bloques pueden
superponerse; entonces ambos filtros se combinan en el orden del proyecto.

Las **transiciones** no son bloques libres: conectan la salida de una toma con
la entrada de la siguiente y por eso permanecen ancladas a cada corte. El campo
**Duración de la transición** controla cuánto material se solapa alrededor de
esos cortes.

Cada cambio del inspector se valida en Python, queda disponible para
deshacer/rehacer y se guarda dentro del `.creacut.json`. El render usa esa
configuración sin repetir Whisper ni la alineación.

El botón **Inicio** de la barra superior sale del proyecto y regresa a la
pantalla principal. Si existen cambios sin guardar, Electron pregunta si deseas
guardarlos, descartarlos o cancelar la salida; cancelar conserva el proyecto
abierto tal como estaba.

## 13. Diapositivas y presentador

En **Inspector → Diapositivas** puedes importar un PDF, un PowerPoint o una
carpeta de imágenes. CREAcut copia los recursos junto al proyecto, dentro de
`.creacut-assets`, y no modifica los originales.

1. Pulsa **Analizar y proponer**.
2. Revisa la correspondencia y los tiempos sugeridos.
3. Pulsa **Usar propuestas** solamente cuando estés conforme.
4. Selecciona una diapositiva para ajustar inicio, fin y estado.
5. Solicita la vista de efectos para mover y redimensionar el presentador.
6. Guarda y exporta un fragmento corto para comprobar el resultado.

PowerPoint instalado permite convertir `.pptx` directamente en Windows. En
otros casos puedes usar LibreOffice o exportar la presentación a PDF. Consulta
[Visor y presentador](VISOR_Y_PRESENTADOR.md) para los detalles del encuadre.
