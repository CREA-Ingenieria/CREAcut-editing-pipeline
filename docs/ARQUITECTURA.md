# Arquitectura y división de CREAcut Beta

Este documento describe la estructura de la versión beta `0.2.0-beta.1`.

## 1. Objetivo de la arquitectura

CREAcut necesita combinar una interfaz fluida con tareas pesadas y bibliotecas
maduras de video e inteligencia artificial. Por eso no se trasladó todo a
JavaScript: Electron resuelve la experiencia de escritorio y Python sigue
siendo la autoridad del dominio y del procesamiento.

Los objetivos de esta división son:

- no duplicar reglas de edición entre Python y React;
- mantener el video y los datos en el equipo del usuario;
- evitar que Whisper o FFmpeg congelen la interfaz;
- validar cada cambio antes de guardarlo;
- permitir sustituir una interfaz sin reescribir el pipeline;
- hacer visibles los límites entre presentación, orquestación y dominio.

## 2. Mapa del repositorio

```text
CREAcut-editing-pipeline-main/
├── creacut/                     # Dominio y pipeline Python
│   ├── pipeline.py              # Orquestación de análisis y render
│   ├── project.py               # Modelo EditProject y validación
│   ├── project_io.py            # Persistencia JSON atómica
│   ├── align.py                 # Alineación y candidatos
│   ├── source_timeline.py       # Regiones fuente y cambios manuales
│   ├── preview.py               # Traducción fuente ↔ edición
│   ├── transcribe.py            # Whisper, caché y selección de dispositivo
│   ├── slides.py                # Importación y propuestas de diapositivas
│   ├── slide_composite.py       # Composición de diapositiva y presentador
│   └── ui/                      # Editor legado PySide6
├── electron-editor/             # Aplicación principal de escritorio
│   ├── python/                  # Adaptadores Electron ↔ Python
│   ├── src/main/                # Proceso principal de Electron
│   ├── src/preload/             # API segura para el renderer
│   ├── src/shared/              # Contratos TypeScript
│   ├── src/renderer/src/        # React: vistas, componentes, hooks y servicios
│   │   └── components/          # Incluye inspector, layout y bienvenida
│   ├── src/renderer/harness.html # Banco visual aislado
│   ├── scripts/                 # Preparación del empaquetado
│   └── docs/                    # Documentación específica de Electron
├── tests/                       # Pruebas Python
├── electron-editor/tests/       # Pruebas TypeScript/React
├── examples/                    # Configuración y datos de ejemplo
├── scripts/                     # Herramientas operativas y editor legado
├── docs/                        # Documentación general
├── pyproject.toml               # Paquete Python
└── requirements.txt             # Instalación amplia de Python
```

## 3. Capas de ejecución

```text
Usuario
  │
  ▼
React: vistas y componentes
  │
  ▼
Servicio del renderer (Facade)
  │
  ▼
Preload: API permitida
  │
  ▼
Electron main: archivos, procesos y ventanas
  ├───────────────┐
  ▼               ▼
bridge.py         jobs.py
interactivo       trabajos largos
  └───────┬───────┘
          ▼
Dominio y pipeline Python
```

### Presentación

React dibuja la aplicación y recibe acciones. No abre archivos, no inicia
procesos y no conoce clases Python. Solo trabaja con objetos definidos en el
contrato compartido.

### Aplicación

`App.tsx` coordina casos de uso y el proceso principal coordina recursos del
sistema. Esta capa decide cuándo abrir un diálogo, iniciar un trabajo o
actualizar la vista, pero no decide qué toma es válida.

### Dominio

`EditProject`, `EditSegment`, candidatos, timeline y validaciones viven en
Python. Si React solicita una operación inválida, Python la rechaza y conserva
el estado anterior.

### Infraestructura

FFmpeg, Whisper, MoviePy, el sistema de archivos, IPC y el servidor de medios
son detalles externos al dominio. Se accede a ellos desde adaptadores concretos.

## 4. Patrones arquitectónicos utilizados

La aplicación no sigue de forma dogmática un único patrón. Combina patrones
pequeños donde aportan claridad.

### Arquitectura por capas

Separa presentación, aplicación, dominio e infraestructura. Evita que un botón
de React termine conteniendo reglas de alineación o código de FFmpeg.

### Core + adaptadores

El paquete `creacut` funciona como Core. Electron, la CLI y PySide6 son
adaptadores que utilizan ese Core. Se parece a una arquitectura hexagonal,
pero no se presenta como una implementación estricta de todos sus conceptos.

### Facade

`creacut-service.ts` concentra la API que puede usar el renderer. Los
componentes no llaman `window.creacut` ni conocen nombres de canales IPC.

### Bridge / Adapter

`bridge.py` traduce mensajes JSON a operaciones de `EditorSession` y
`EditProject`. El preload traduce llamadas TypeScript a IPC. Cada puente evita
que el modelo de una tecnología se filtre directamente a otra.

### Application Controller

`App.tsx` coordina la pantalla y los casos de uso. No dibuja los detalles del
timeline ni implementa la reproducción.

### Container / Presentational Components

`views/` define pantallas completas y `components/` bloques visuales. Los
componentes reciben propiedades y callbacks en vez de buscar datos globales.

### Controller Hook

`usePreviewPlayback` encapsula el estado del elemento `<video>`, los saltos
pendientes, el modo fuente/propuesta y la coordinación de eventos multimedia.

### Domain Service

Servicios como `preview-navigation.ts`, `preview-timeline.ts` y
`seek-coordinator.ts` contienen reglas puras sin React ni Electron. Son fáciles
de razonar y reutilizar.

### DTO y contrato explícito

`src/shared/contracts.ts` define los objetos que cruzan procesos. Estos DTO no
son las clases de dominio Python; son representaciones serializables para la UI.

### Command / Job

Análisis, render y lote se representan como trabajos con identificador,
progreso, resultado, error y cancelación. Solo hay uno largo activo para evitar
competencia por GPU y memoria.

### Observer por eventos

`JobRunner` publica eventos y el renderer se suscribe mediante `onJobEvent`.
Así el trabajo no necesita conocer el diálogo que muestra su progreso.

### Proyecciones derivadas

El proyecto guarda decisiones canónicas. Timeline y preview son proyecciones
calculadas. Esto evita persistir dos verdades que podrían contradecirse.

### Memento y deltas compactos

La recuperación usa un snapshot validado; undo/redo conserva cambios compactos
de selección o timeline. No se duplica toda la transcripción en cada paso.

## 5. Por qué dos procesos Python

`bridge.py` permanece activo para acciones rápidas: abrir, seleccionar, editar,
guardar y generar medios del timeline. `jobs.py` se inicia para operaciones
largas: análisis, render y lote.

Separarlos permite cancelar un trabajo, conservar la sesión interactiva y
evitar que un fallo pesado destruya el estado abierto. También simplifica la
regla de un único trabajo intensivo a la vez.

## 6. Por qué el video se sirve por HTTP local

El renderer aislado no recibe acceso general al disco. El proceso principal
registra archivos permitidos con tokens aleatorios y los sirve en
`127.0.0.1` mediante un puerto efímero.

El servidor implementa rangos HTTP para que Chromium solicite solo los bytes
necesarios durante un seek. No es un backend web público: se cierra con la
aplicación y solo sirve rutas registradas.

## 7. Flujo de datos de una edición

```text
Clic en “Usar esta toma”
        │
        ▼
InspectorPanel callback
        │
        ▼
App → creacutService
        │
        ▼
preload → IPC project:select-candidate
        │
        ▼
main → bridge.select_candidate
        │
        ▼
EditorSession valida y modifica EditProject
        │
        ▼
ProjectView actualizado
        │
        ▼
React vuelve a dibujar
```

El renderer no aplica el cambio de forma optimista. Espera la versión aceptada
por Python.

## 8. Seguridad

- `contextIsolation: true`.
- `nodeIntegration: false`.
- `sandbox: true` en el renderer.
- Preload con API limitada.
- Nuevas ventanas y navegación externa bloqueadas.
- Métodos del puente en una tabla permitida.
- Proyectos validados antes de abrir, modificar o guardar.
- Servidor de medios limitado a localhost y archivos registrados.
- Instancia única para evitar escrituras simultáneas en cachés de Chromium.

## 9. Persistencia y procedencia

El `.creacut.json` guarda el esquema, la fuente, el guion, la transcripción,
los candidatos, la selección y la configuración. También conserva hashes y
metadatos que permiten detectar recuperaciones o fuentes incompatibles.

`project_io.save_project()` escribe de forma atómica: primero crea un temporal
y después reemplaza el destino. No permite sobrescribir accidentalmente el
video o el guion.

## 10. Cómo decidir dónde agregar código

| Cambio | Ubicación recomendada |
|---|---|
| Regla de edición o validación | `creacut/` |
| Persistencia del proyecto | `project.py` / `project_io.py` |
| Importación y tiempos de diapositivas | `slides.py` |
| Composición de diapositivas | `slide_composite.py` |
| Operación interactiva nueva | `bridge.py` + contrato + IPC + servicio |
| Trabajo pesado nuevo | `jobs.py` + `JobRunner` |
| Regla pura de preview | `renderer/src/services/` |
| Estado del reproductor | `usePreviewPlayback.ts` |
| Pantalla completa | `views/` |
| Bloque visual reutilizable | `components/` |
| Cuerpo del inspector | `components/inspector/` |
| Separadores y armazón | `components/layout/` |
| Acceso a archivos o diálogos | proceso `main` |

## 11. Alternativas descartadas

### Reescribir el pipeline en JavaScript

Duplicaría lógica probada, dificultaría la compatibilidad de proyectos y
obligaría a sustituir bibliotecas Python de video e IA.

### Ejecutar Whisper dentro del renderer

Rompería el aislamiento, bloquearía la interfaz y expondría APIs de sistema.

### Usar un servidor remoto

Agregaría subida de videos, autenticación, costes y riesgos de privacidad. El
objetivo actual es procesamiento local.

### Guardar el MP4 como estado editable

Haría cada cambio lento y destructivo. Guardar decisiones permite regenerar el
resultado y conservar siempre la fuente.

## 12. Límites actuales de la arquitectura

- La instalación deja un backend Python sin `.venv` en el equipo del usuario:
  construido desde PyPI en la máquina del usuario: por el asistente en Windows y
  en el primer arranque en macOS.
- El preview no ejecuta la cadena completa de render.
- El DMG de macOS es solo para Apple Silicon; debe construirse y verificarse en
  un Mac con ese chip.
- No hay firma Authenticode ni notarización Apple.
- El renderer depende de codecs compatibles con Chromium.
- El selector de Whisper todavía no usa MPS en macOS.

Para detalles de implementación consulta la
[arquitectura Electron](../electron-editor/docs/ARQUITECTURA_BACKEND_Y_PIPELINE.md)
y la [arquitectura del frontend](../electron-editor/docs/ARQUITECTURA_FRONTEND.md).
