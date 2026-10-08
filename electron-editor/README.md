# Editor Electron de CREAcut Beta

> **Estado:** versión beta `0.2.0-beta.1`. Todavía no es una aplicación final
> ni está probada por completo en todos los sistemas, GPU y formatos de video.

Frontend y desarrollo web: **Ángel Peñaranda**. Pipeline y procesamiento:
**Sebastián Suárez**.

Esta es la interfaz principal de CREAcut. Usa tecnologías web dentro de una
aplicación de escritorio, pero todo el procesamiento continúa ejecutándose
localmente con Python.

## 1. Responsabilidad del editor

Electron se encarga de:

- ventanas, menús y diálogos del sistema;
- reproducción de video;
- transcripción y guion visibles;
- timeline, waveform y miniaturas;
- biblioteca de diapositivas y presentador ajustable;
- selección de tomas y cambios manuales;
- guardado, recuperación y recientes;
- inicio y cancelación de trabajos Python;
- creación de instaladores.

Electron no implementa Whisper, alineación, chroma ni render. Esas reglas
siguen en `../creacut`.

## 2. Tecnologías

| Tecnología | Uso |
|---|---|
| Electron | Aplicación de escritorio y procesos aislados. |
| React | Interfaz declarativa. |
| TypeScript | Contratos y comprobación estática. |
| Vite / electron-vite | Desarrollo y compilación. |
| Tailwind CSS | Estilos y temas. |
| Radix UI | Primitivas accesibles. |
| Python | Backend interactivo y trabajos largos. |
| electron-builder | `.exe`, `.app` y `.dmg`. |

## 3. Procesos de Electron

```text
renderer React
      │ window.creacut
      ▼
preload seguro
      │ IPC
      ▼
main Electron
      │ JSON Lines / procesos
      ▼
backend Python
```

- **Renderer:** solo UI; no tiene acceso a Node.js.
- **Preload:** publica una API mínima y tipada.
- **Main:** controla archivos, procesos, ventana, recuperación y medios.
- **Python:** valida y modifica el proyecto.

## 4. Estructura

```text
electron-editor/
├── python/
│   ├── bridge.py                  # Sesión interactiva persistente
│   ├── jobs.py                    # Análisis, render y lote
│   └── recovery_codec.py          # Compatibilidad de recuperaciones
├── scripts/
│   ├── prepare-backend-setup.mjs  # Fuentes y `uv` para el instalador
│   └── verify-bundle.mjs          # Falla si el paquete lleva binarios
├── src/
│   ├── main/                      # Proceso principal
│   ├── preload/                   # API contextBridge
│   ├── shared/contracts.ts        # Contrato entre capas
│   └── renderer/src/
│       ├── views/                 # Pantallas completas
│       ├── components/            # Bloques visuales, inspector y layout
│       ├── hooks/                 # Controladores React
│       ├── services/              # Fachadas y reglas puras
│       └── types/                 # Tipos exclusivos del renderer
├── src/renderer/harness.html       # Banco visual sin Electron ni Python
├── vite.harness.config.ts          # Configuración del banco visual
├── tests/                         # Pruebas TypeScript/React
├── docs/                          # Arquitectura e instaladores
└── package.json                   # Scripts y configuración de build
```

## 5. Requisitos

- Node.js y pnpm para desarrollo o compilación.
- Una `.venv` de Python preparada en la raíz, solo para desarrollo y build.
- FFmpeg ya no hace falta en el `PATH` para transcribir durante el desarrollo:
  `imageio-ffmpeg`, que instala `requirements.txt`, lo provee. Los instaladores
  traen ese mismo FFmpeg desde PyPI al preparar el entorno.
- En Windows, Torch con CUDA si se desea GPU.

Guía completa: [`../docs/installation.md`](../docs/installation.md).

## 6. Instalar dependencias

```bash
cd electron-editor
pnpm install
```

## 7. Ejecutar en desarrollo

Windows:

```powershell
$env:CREACUT_PYTHON = (Resolve-Path ..\.venv\Scripts\python.exe).Path
pnpm dev
```

macOS:

```bash
export CREACUT_PYTHON="$(cd .. && pwd)/.venv/bin/python"
pnpm dev
```

La pantalla inicial debe mostrar **Backend Python conectado** y el intérprete
esperado.

## 8. Scripts de package.json

| Script | Resultado |
|---|---|
| `pnpm dev` | Vite + Electron con recarga. |
| `pnpm run typecheck` | Comprueba TypeScript sin emitir archivos. |
| `pnpm run build` | Genera `out/`. |
| `pnpm test` | Ejecuta Vitest. |
| `pnpm run pack:win` | Genera `dist/win-unpacked/`. |
| `pnpm run dist:win` | Genera el `.zip` con el instalador NSIS. |
| `pnpm run pack:mac` | Genera `.app` sin DMG en una Mac. |
| `pnpm run dist:mac` | Genera el DMG arm64 en un Mac con Apple Silicon. |

## 9. Funciones implementadas

- pantalla inicial animada y temas claro/oscuro;
- backend y dispositivo visibles;
- proyecto nuevo y apertura de existentes;
- proyectos recientes y recuperación;
- video original y edición propuesta;
- navegación por clips editados;
- selección desde transcripción, guion, timeline e inspector;
- resaltado sincronizado de transcripción y guion durante la reproducción;
- seguimiento horizontal del playhead cuando un salto queda fuera de vista;
- selección y restauración de tomas;
- inspector de proyecto, propiedades de selección y biblioteca de diapositivas;
- panel de recursos con transcripción y guion;
- paneles redimensionables y plegables;
- vista previa del fotograma actual con chroma, fondo y corrección de piel reales;
- filtros temporales previsualizados durante toda la reproducción;
- importación de PDF, PowerPoint o carpetas de imágenes como diapositivas;
- propuestas de tiempo para diapositivas y ajuste visual del presentador;
- pista de efectos con bloques movibles y extremos redimensionables;
- transiciones de corte, disolvencia, fundido a negro, barrido y deslizamiento;
- edición persistente de transición, chroma, fondo, corrección de piel,
  overlays y normalización de audio;
- salida segura al inicio con confirmación cuando hay cambios sin guardar;
- conservación, descarte, restauración, división y movimiento de regiones;
- undo/redo;
- miniaturas, waveform y zoom;
- guardado y guardar como;
- exportación MP4 con progreso y cancelación;
- lote con identificación automática uno a uno;
- instancia única de la aplicación.

## 10. Trabajos largos

`jobs.py` ejecuta análisis, render o lote en un proceso separado. `JobRunner`
envía progreso al renderer y permite cancelar. Solo se admite un trabajo largo
activo, evitando que dos Whisper compitan por la GPU.

El puente persistente continúa disponible para operaciones cortas del proyecto.

## 11. Lote automático

El usuario selecciona listas de videos y guiones con igual cantidad. Python
identifica el mejor guion disponible para cada video y lo retira de los
candidatos siguientes. El resultado muestra pareja, puntaje y proyecto.

El emparejamiento es secuencial; cuando varios guiones comienzan casi igual, la
persona debe revisar los puntajes y proyectos.

## 12. Seguridad

- `contextIsolation` activado.
- `nodeIntegration` desactivado.
- renderer con sandbox.
- preload limitado a `CreacutApi`.
- ventanas externas y navegación bloqueadas.
- medios servidos solo desde `127.0.0.1` con tokens.
- proyectos validados en Python.

## 13. Instaladores

### Windows

```powershell
pnpm run dist:win
```

Genera `dist\windows-release\CREAcut-Beta-0.2-Windows-x64.zip`, con el instalador
dentro. El asistente instala **CREAcut Beta**, construye el backend y crea accesos
directos en el escritorio y menú Inicio.

### macOS

```bash
pnpm run dist:mac
```

Genera `dist/CREAcut-Beta-0.2-arm64.dmg` en un Mac con Apple Silicon. El usuario arrastra
**CREAcut Beta** a Aplicaciones.

Ningún instalador congela el backend: llevan las fuentes Python y `uv`, y
construyen el entorno desde PyPI (Windows al instalar, con PyTorch CPU y el
paquete CUDA como opción; macOS en el primer arranque).
La `.venv` solo se usa para construir y no se
necesita en el equipo final. El instalador de Windows prepara Whisper y Gemma 4
durante la instalación; consulta [Modelos](../docs/modelos.md). En macOS, la
primera vez que abres la app prepara Whisper `large-v3` y `medium`.

## 14. Validación manual mínima

1. Comprobar backend y dispositivo.
2. Abrir un proyecto y reproducir audio/video.
3. Seleccionar guion, diálogo y toma; verificar el seek.
4. Agregar un filtro temporal y mover/redimensionar su bloque en la pista EFECTOS.
5. Reproducir atravesando sus límites y comprobar que se activa y desactiva.
6. Elegir chroma o corrección de piel y pulsar **Previsualizar fotograma actual**.
7. Elegir una transición animada y exportar un MP4 corto para comprobarla.
8. Cambiar una toma y una región.
9. Comprobar undo/redo y guardado.
10. Pulsar **Inicio** con cambios y comprobar guardar, descartar y cancelar.
11. Cerrar con cambios y validar recuperación.
12. Ejecutar un lote pequeño y revisar emparejamientos.

## 15. Pruebas existentes

Las pruebas de `tests/` cubren servicios de navegación, coordinación de seek,
servidor de medios, instancia única y logo. La recuperación también tiene
pruebas Python en la raíz. La existencia de estas pruebas no sustituye una
prueba manual con codecs, GPU y archivos reales.

## 16. Documentación relacionada

- [Arquitectura del backend y pipeline](docs/ARQUITECTURA_BACKEND_Y_PIPELINE.md)
- [Arquitectura del frontend](docs/ARQUITECTURA_FRONTEND.md)
- [Instalador Windows](docs/INSTALADOR_WINDOWS.md)
- [Instalador macOS](docs/INSTALADOR_MACOS.md)
- [Arquitectura general](../docs/ARQUITECTURA.md)
- [Paquetes](../docs/PAQUETES_Y_DEPENDENCIAS.md)

## 17. Límites actuales

- El fotograma de efectos cubre chroma, fondo y piel; las transiciones,
  overlays, bookends y el audio se comprueban en el MP4 final.
- El backend de Windows se instala desde PyPI: la entrega es ligera, pero la
  instalación depende de la conexión.
- El DMG no puede considerarse verificado hasta probarlo en macOS.
- El DMG de macOS es solo para Apple Silicon.
- La etiqueta Beta debe mantenerse hasta completar la validación funcional y
  de instalación necesaria para una versión estable.
- No hay firma de Windows ni notarización Apple.
- MPS todavía no se selecciona para Whisper.
