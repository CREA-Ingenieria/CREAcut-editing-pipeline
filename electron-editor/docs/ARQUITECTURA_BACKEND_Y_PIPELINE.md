# Arquitectura de Electron, backend y pipeline de CREAcut Beta

Este documento explica cómo se conectan las partes sin asumir experiencia en
programación. Corresponde a la beta `0.2.0-beta.1`.

## Idea principal

- **React** muestra botones, paneles, video y timeline.
- **Electron** permite usar ventanas, archivos y procesos del computador.
- **Python** valida el proyecto y procesa el video.
- **El pipeline** transcribe, propone la edición y exporta el MP4.

Todo ocurre localmente. Los videos no se suben a un servidor web.

## Recorrido de una acción

```text
Persona pulsa un botón
        │
        ▼
React envía una petición permitida
        │
        ▼
Preload la comunica al proceso principal
        │
        ▼
Electron llama al backend
        │
        ▼
Python valida y cambia EditProject
        │
        ▼
React recibe y muestra ProjectView
```

React nunca modifica el proyecto por su cuenta. Si Python rechaza un cambio, el
estado anterior se conserva.

## Capas y archivos

### Interfaz React

`src/renderer/src/` contiene:

- `App.tsx`: coordina abrir, guardar, analizar y exportar;
- `views/`: arma las pantallas completas;
- `components/`: visor, recursos, timeline, inspector y bienvenida;
- `hooks/`: reproducción, paneles, geometría y animaciones;
- `services/`: reglas puras y fachada hacia Electron;
- `types/`: tipos que solo necesita la interfaz.

### Preload

`src/preload/index.ts` publica `window.creacut`. Es una lista limitada de
operaciones permitidas. El renderer no puede usar directamente el sistema de
archivos ni crear procesos.

### Proceso principal de Electron

`src/main/` contiene:

- `index.ts`: ventana, menús, diálogos y canales IPC;
- `bridge-client.ts`: comunicación interactiva con Python;
- `job-runner.ts`: análisis, render y lotes;
- `backend-runtime.ts`: localiza Python en desarrollo o el entorno preparado;
- `macos-backend-setup.ts`: prepara el entorno Python en el primer arranque de macOS;
- `media-server.ts`: sirve medios autorizados en `127.0.0.1`;
- `recent-project-previews.ts`: imágenes para proyectos recientes;
- `single-instance.ts`: evita abrir dos instancias sobre la misma caché.

### Adaptadores Python

`electron-editor/python/` contiene:

- `bridge.py`: sesión interactiva para abrir, editar y guardar;
- `jobs.py`: análisis, render y procesamiento por lote;
- `recovery_codec.py`: recuperación compatible y validada;
- `verify_backend.py`: comprueba el entorno recién preparado.

### Core Python

`../creacut/` contiene las reglas del proyecto:

- `project.py` y `project_io.py`: modelo, validación y guardado;
- `align.py`: correspondencia entre voz y guion;
- `source_timeline.py` y `preview.py`: regiones y tiempos;
- `transcribe.py`: Whisper y dispositivo;
- `pipeline.py`: análisis y render;
- `slides.py`: importación y propuestas de diapositivas;
- `slide_composite.py`: composición de diapositiva y presentador;
- módulos de chroma, piel, overlays, cortes y audio.

## Dos tipos de proceso Python

El puente permanece abierto para operaciones breves: seleccionar una toma,
mover un límite, cambiar una diapositiva o guardar.

Los trabajos largos se ejecutan en otro proceso: Whisper, análisis, render o
lote. De esta manera se pueden cancelar y no bloquean la sesión interactiva.
Solo se permite un trabajo largo a la vez para no hacer competir dos procesos
por la GPU y la memoria.

En desarrollo, Electron ejecuta `bridge.py` y `jobs.py` mediante el Python de
`.venv`. En una aplicación instalada ejecuta los mismos archivos con el Python
del entorno que el instalador preparó en el equipo del usuario.

## Entorno del instalador

La persona que instala CREAcut Beta no necesita Python ni `.venv`. Tampoco se
congela el backend: el instalador lleva las fuentes de `creacut/` y
`electron-editor/python/`, más `uv`, y el entorno se arma desde PyPI en su
equipo.

```text
fuentes Python + uv (en el instalador)
              │
              ▼
uv crea Python 3.12 + dependencias desde PyPI
              │
              ▼
Electron ejecuta bridge.py y jobs.py con ese Python
```

- Windows lo construye durante NSIS con `resources/install-backend.ps1`.
- macOS lo construye en el primer arranque con `src/main/macos-backend-setup.ts`
  y muestra la pantalla **Preparando CREAcut para tu Mac**.
- `scripts/prepare-backend-setup.mjs` deja `uv` y el manifiesto de versiones.
- `scripts/verify-bundle.mjs` hace fallar el empaquetado de macOS si el DMG lleva
  FFmpeg, bibliotecas nativas o `site-packages`.

El instalador ya no crea ni consulta `backend-location.json`.

## Por qué el DMG es solo Apple Silicon

El DMG se publica únicamente para `arm64` (Apple Silicon, M1 o posterior). Como
el entorno se arma en el equipo del usuario, no hay binarios de Python que
duplicar por arquitectura; la compatibilidad se limita a lo que se ha probado.

## Creación y análisis

1. La persona elige video, guion y ruta del proyecto.
2. Electron inicia un trabajo `analysis`.
3. Whisper crea o reutiliza la transcripción.
4. El pipeline relaciona la transcripción con el guion.
5. Python crea `EditProject` con candidatos y decisiones.
6. El proyecto se guarda como `.creacut.json`.
7. Electron lo abre para revisión.

El proyecto de salida no es el MP4. Es el archivo editable que conserva las
decisiones.

## Apertura y edición

`bridge.py` mantiene un `EditorSession`. Las operaciones permiten:

- elegir o restaurar una toma;
- conservar, descartar, dividir o ajustar regiones;
- cambiar ajustes de render;
- crear, mover o eliminar filtros temporales;
- importar y editar diapositivas;
- deshacer y rehacer;
- guardar y crear recuperación.

Cada operación valida tipos, tiempos, identificadores y orden cronológico antes
de modificar el proyecto.

## Diapositivas y presentador

El bridge puede importar PDF, PowerPoint o carpetas de imágenes. `slides.py`
copia los recursos a `.creacut-assets`, extrae texto y propone tiempos usando la
transcripción. Las propuestas solo se activan cuando la persona pulsa **Usar
propuestas**.

La vista de efectos separa el fondo de la diapositiva y la capa del presentador.
`slide_composite.py` aplica el mismo encuadre al MP4 final.

## Timeline y medios

El video y las imágenes se registran en `media-server.ts` con tokens aleatorios.
Solo se sirven desde `127.0.0.1` y solo mientras la aplicación está abierta.
Los rangos HTTP permiten saltar en el video sin cargarlo completo.

Miniaturas y waveform se guardan en `.creacut-cache`. Son regenerables y nunca
modifican el video fuente.

## Guardado y recuperación

`project_io.save_project()` escribe primero un archivo temporal y después
reemplaza el destino. Electron mantiene una recuperación cuando hay cambios sin
guardar. Python comprueba que esa recuperación corresponda al proyecto original
antes de abrirla.

## Exportación MP4

1. Electron guarda el proyecto.
2. Inicia un trabajo `render`.
3. Python compila los rangos aprobados.
4. El pipeline aplica cortes, transiciones, efectos, chroma, diapositivas,
   overlays, inicio/cierre y audio.
5. FFmpeg escribe el MP4 final.

No se repiten Whisper ni la alineación. El render depende de que el video fuente
siga disponible.

## Procesamiento por lote

El lote recibe videos y guiones. Para cada video, Python busca el guion con
mayor coincidencia, lo retira de los candidatos siguientes, copia los archivos
a una carpeta propia y crea el proyecto editable. La persona debe revisar las
coincidencias antes de exportar.

## Seguridad

- `contextIsolation` está activado.
- `nodeIntegration` está desactivado.
- El renderer usa sandbox.
- Preload expone una API limitada.
- Se bloquean ventanas y navegaciones externas.
- Los medios se sirven únicamente desde localhost con tokens.
- Python valida proyectos y recuperaciones.
- Solo se permite una instancia de la aplicación.

## Desarrollo y aplicación instalada

| Situación | Backend utilizado |
|---|---|
| `pnpm dev` | Python de `.venv` y scripts fuente. |
| `.exe` instalado | Python del entorno que construyó el asistente. |
| `.app` instalada | Python del entorno que construyó el primer arranque. |

## Límites de la beta

- Los instaladores pueden ser grandes por PyTorch y bibliotecas multimedia.
- Windows prepara Whisper y Gemma 4 mediante `setup-models` durante la instalación.
  En macOS los prepara la pantalla de primer arranque; solo en desarrollo
  Whisper puede descargarse en el primer uso.
- Windows se construye actualmente para x64.
- El DMG de macOS es solo para Apple Silicon.
- Los instaladores no están firmados ni notarizados.
- CUDA depende de las bibliotecas empaquetadas y del controlador del equipo.
- El DMG todavía requiere construcción y comprobación real en una Mac.
- El preview es aproximado; el MP4 es el resultado definitivo.
