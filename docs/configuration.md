# Configuración de CREAcut Beta

> Esta guía corresponde a la beta `0.2.0-beta.1`. La configuración del pipeline
> puede cambiar mientras se completa la validación de la aplicación.

CREAcut combina valores predeterminados, un archivo `creacut.yml` y argumentos
de terminal. Solo necesitas escribir las claves que quieras cambiar.

## 1. Orden de carga

1. `--config <ruta>` si se especifica.
2. `./creacut.yml` en el directorio actual.
3. `~/.config/creacut/creacut.yml`.
4. Valores de `creacut/config.py`.
5. Argumentos CLI, que tienen la mayor prioridad.

La mezcla es profunda: cambiar `whisper.model` no elimina
`whisper.language`. Copia [`examples/creacut.yml`](../examples/creacut.yml)
como punto de partida.

## 2. Whisper

| Clave | Predeterminado | Función |
|---|---|---|
| `whisper.model` | `large-v3` | Modelo solicitado. |
| `whisper.prompt` | `""` | Vocabulario o contexto inicial. |
| `whisper.language` | `es` | Idioma ISO de la transcripción. |

Modelos grandes consumen más tiempo y VRAM. En CUDA, si un modelo `large*`
agota memoria, CREAcut puede reintentar `medium` en la misma GPU. No cambia a
CPU silenciosamente.

## 3. Guiones

| Clave | Predeterminado | Función |
|---|---|---|
| `scripts.directory` | `null` | Carpeta de Markdown para identificación automática. |
| `scripts.format` | `markdown` | Campo reservado para el formato esperado; el parser actual usa Markdown. |

Si se pasa `--script`, esa ruta gana. El lote Electron envía una lista explícita
de candidatos y no depende de `scripts.directory`.

## 4. Chroma

| Clave | Predeterminado | Función |
|---|---:|---|
| `chroma.enabled` | `true` | Activa reemplazo de fondo verde. |
| `chroma.color` | `[24, 238, 28]` | Color RGB objetivo. |
| `chroma.inner_threshold` | `40` | Umbral de fondo completamente reemplazado. |
| `chroma.outer_threshold` | `100` | Umbral de sujeto completamente opaco. |
| `chroma.blur_radius` | `3` | Suavizado del alfa. |
| `chroma.morph_close_radius` | `2` | Cierre morfológico de huecos. |
| `chroma.pre_blur_radius` | `1` | Suavizado previo para ruido de compresión. |
| `chroma.despill_strength` | `0.8` | Reducción de reflejo verde en bordes. |
| `chroma.subject_despill_strength` | `0.8` | Reducción de verde del lado del sujeto. |
| `chroma.s_min` | `100` | Saturación HSV mínima para considerar verde. |
| `chroma.v_min` | `120` | Brillo HSV mínimo para considerar verde. |

`inner_threshold` debe ser menor que `outer_threshold`. Cambios grandes pueden
eliminar partes del sujeto; prueba con un fragmento corto.

## 5. Fondo

| Clave | Predeterminado | Función |
|---|---|---|
| `background.image` | `null` | Imagen que reemplaza el fondo. |

También puede indicarse con `--bg-image`. En Electron se selecciona desde el
formulario de proyecto nuevo.

## 6. Corrección de piel

| Clave | Predeterminado | Función |
|---|---:|---|
| `skin_correction.enabled` | `false` | Activa corrección. |
| `skin_correction.hue_shift` | `-12` | Cambio de tono. |
| `skin_correction.sat_scale` | `0.88` | Multiplicador de saturación. |
| `skin_correction.sat_clamp` | `155` | Saturación máxima. |
| `skin_correction.strength` | `1.0` | Mezcla con el original, de 0 a 1. |

## 7. Overlays

### Listas

| Clave | Predeterminado | Función |
|---|---|---|
| `overlays.lists.enabled` | `true` | Detecta listas habladas. |
| `overlays.lists.llm_provider` | `auto` | `auto`, `ollama`, `claude` o `regex`. |
| `overlays.lists.ollama_model` | `gemma4` | Modelo local. |
| `overlays.lists.claude_model` | `claude-haiku-4-5-20251001` | Modelo Anthropic. |

`auto` intenta Ollama, luego Claude y finalmente regex. La ausencia de un
proveedor no impide el fallback.

### Términos

| Clave | Predeterminado | Función |
|---|---|---|
| `overlays.terms.enabled` | `true` | Activa términos de vocabulario. |
| `overlays.terms.vocab_file` | `null` | JSON de términos y definiciones. |
| `overlays.terms.display_duration` | `5.0` | Duración en segundos. |

Formato:

```json
[
  {"term": "presión", "definition": "Fuerza aplicada por unidad de área"}
]
```

### Ecuaciones

| Clave | Predeterminado | Función |
|---|---|---|
| `overlays.equations.enabled` | `false` | Activa ecuaciones. |
| `overlays.equations.specs_file` | `null` | Especificación JSON. |

`--equation-specs` define el archivo y activa esta sección.

### Texto en negrita

| Clave | Predeterminado | Función |
|---|---|---|
| `overlays.bold_cards.enabled` | `true` | Convierte `**texto**` del guion en tarjetas. |

## 8. Estilo visual

| Clave | Predeterminado | Función |
|---|---|---|
| `styling.font` | `auto` | Fuente automática o ruta `.ttf/.otf`. |
| `styling.accent_colors` | cinco RGB | Colores rotativos de overlays. |
| `styling.panel_bg` | `[243,245,248,230]` | Fondo RGBA de paneles. |
| `styling.panel_radius` | `16` | Radio de esquinas. |

## 9. Inicio y cierre

| Clave | Predeterminado | Función |
|---|---:|---|
| `bookends.intro_video` | `null` | Video de introducción. |
| `bookends.closing_image` | `null` | Imagen de cierre. |
| `bookends.closing_duration` | `5.0` | Duración del cierre. |

## 10. Audio y transiciones

| Clave | Predeterminado | Función |
|---|---:|---|
| `audio.normalize` | `true` | Normalización EBU R128. |
| `audio.fade_duration` | `0.06` | Fade corto en cortes. |
| `transitions.type` | `dissolve` | Estilo: `cut`, `dissolve`, `fade_black`, `wipe_left` o `slide_left`. |
| `transitions.crossfade` | `0.20` | Duración de la transición animada, entre `0.0` y `0.5` segundos. |

`cut` concatena las tomas sin solaparlas. Los demás estilos solapan imagen y
audio; `dissolve` mezcla ambas tomas, `fade_black` pasa por negro, `wipe_left`
revela la toma entrante de izquierda a derecha y `slide_left` desplaza ambas
tomas horizontalmente.

## 10.1. Filtros visuales temporales

`visual_effects.ranges` contiene bloques medidos sobre el tiempo del video
fuente. El editor Electron los crea, mueve y redimensiona; normalmente no es
necesario escribirlos a mano.

```yaml
visual_effects:
  ranges:
    - id: color-intro
      kind: cinematic
      start_s: 5.0
      end_s: 12.5
```

Los tipos permitidos son `cinematic`, `warm`, `cool`, `black_white`, `vintage`
y `vivid`. Los rangos pueden superponerse; en ese caso se aplican en el orden
en el que aparecen en el proyecto.

## 11. Retomas y cortes

| Clave | Predeterminado | Función |
|---|---:|---|
| `retakes.restart_words` | lista | Expresiones de reinicio. |
| `retakes.merge_gap` | `5.0` | Gap máximo para fusionar rangos. |
| `retakes.split_gap` | `4.0` | Gap para dividir rangos. |
| `retakes.min_pre_gap_dur` | `1.0` | Duración mínima previa. |
| `retakes.max_word_gap` | `8.0` | Palabra fantasma sospechosa. |
| `retakes.match_threshold` | `0.55` | Puntaje mínimo de candidato. |
| `retakes.good_match_threshold` | `0.6` | Puntaje considerado bueno. |
| `retakes.pad_start` | `0.1` | Margen inicial. |
| `retakes.pad_end` | `0.25` | Margen final. |

Los cambios manuales del timeline se aplican después como decisiones explícitas
y no vuelven a recibir padding automático durante el render.

## 12. Salida

| Clave | Predeterminado | Función |
|---|---|---|
| `output.directory` | `null` | `null` usa la carpeta del video. |
| `output.suffix` | `_edited` | Sufijo cuando no se indica `--output`. |

El proyecto `.creacut.json` y el MP4 final son salidas diferentes.

## 13. Argumentos CLI

| Argumento | Efecto real |
|---|---|
| `--script` | Guion explícito. |
| `--output` | MP4 final. |
| `--config` | YAML explícito. |
| `--dry-run` | Analiza sin exportar video. |
| `--no-chroma` | `chroma.enabled=false`. |
| `--chroma-color R G B` | Reemplaza `chroma.color`. |
| `--bg-image PATH` | Define `background.image`. |
| `--skin-correction` | Activa corrección de piel. |
| `--vocab PATH` | Define vocabulario. |
| `--equation-specs PATH` | Define y activa ecuaciones. |
| `--no-normalize` | Desactiva normalización. |
| `--project-output PATH` | Guarda proyecto editable. |
| `--project-only` | Se detiene después del proyecto; exige `--project-output`. |
| `--json PATH` | Exporta diagnóstico de alineación. |

### Limitaciones actuales de dos flags

Aunque la ayuda de terminal usa nombres generales:

- `--no-overlays` modifica actualmente `overlays.lists.enabled`; para desactivar
  términos, negritas o ecuaciones hazlo también en YAML.
- `--no-bookends` limpia actualmente `bookends.intro_video`; para asegurar que
  no haya cierre define también `bookends.closing_image: null`.

Esta documentación describe el comportamiento del código actual, no solo la
intención del nombre del argumento.

## 14. Ejemplo mínimo para análisis editable

```yaml
whisper:
  model: medium
  language: es

chroma:
  enabled: false

overlays:
  lists:
    enabled: false
  terms:
    enabled: false
  equations:
    enabled: false
  bold_cards:
    enabled: false

audio:
  normalize: false
```

## 15. Ejemplo de producción

```yaml
whisper:
  model: large-v3
  language: es
  prompt: "sistemas hidráulicos, presión, caudal"

chroma:
  enabled: true
  color: [24, 238, 28]

background:
  image: ./assets/fondo.png

bookends:
  intro_video: ./assets/intro.mp4
  closing_image: ./assets/cierre.png
  closing_duration: 5.0

audio:
  normalize: true
```

## 16. Configuración guardada en el proyecto

Al crear un `.creacut.json`, la configuración efectiva se guarda dentro del
proyecto. El render reutiliza esos valores salvo que la CLI de
`render-project` reciba `--config`, que reemplaza la configuración guardada.
