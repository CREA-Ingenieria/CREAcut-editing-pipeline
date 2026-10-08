# Arquitectura del frontend de CREAcut Beta

Este documento describe la estructura de la versión beta `0.2.0-beta.1`. El
frontend muestra y organiza la edición; las reglas importantes siguen viviendo
en Python.

## Vista sencilla

```text
Persona usa la interfaz
        │
        ▼
React muestra pantallas y recoge acciones
        │
        ▼
Electron accede a archivos y procesos permitidos
        │
        ▼
Python valida y modifica el proyecto
```

React no corta el video ni decide qué toma es válida. Envía la acción a Python
y espera el proyecto actualizado.

## Estructura actual

```text
src/renderer/src/
├── App.tsx                         Estado general y casos de uso
├── Dialogs.tsx                     Nuevo proyecto y progreso
├── Timeline.tsx                    Dibujo y gestos del timeline
├── views/
│   ├── WelcomeView.tsx             Pantalla de bienvenida
│   └── EditorView.tsx              Composición del editor
├── components/
│   ├── batch/                      Ventana de procesamiento por lote
│   ├── inspector/
│   │   ├── ProjectInspector.tsx    Ajustes generales
│   │   └── SelectionInspector.tsx  Elemento seleccionado
│   ├── layout/
│   │   └── PanelDivider.tsx        Separadores redimensionables
│   ├── ui/                         Botones, pestañas y campos reutilizables
│   ├── welcome/                    Marca y proyectos recientes
│   ├── AssetsPanel.tsx             Transcripción y guion
│   ├── EditorTopbar.tsx            Acciones principales
│   ├── InspectorPanel.tsx          Proyecto y diapositivas
│   ├── ScriptPanel.tsx             Guion navegable
│   ├── SlidesLibrary.tsx           Biblioteca de diapositivas
│   ├── SlidePresenterHandle.tsx    Caja editable del presentador
│   ├── TakeInspectorTab.tsx        Tomas candidatas
│   ├── TimelinePanel.tsx           Contenedor del timeline
│   ├── TimelineTrackGutter.tsx     Nombres de pistas
│   ├── TransitionOverlay.tsx       Transición aproximada
│   └── VideoPreview.tsx            Video y controles
├── hooks/
│   ├── useMediaRect.ts             Rectángulo real del video
│   ├── usePanelLayout.ts           Tamaño y plegado de paneles
│   ├── usePreviewPlayback.ts       Reproducción y saltos
│   ├── useProjectStack.ts          Proyectos recientes apilados
│   ├── useSmoothScroller.ts        Scroll de bienvenida
│   └── useTransitionPreview.ts     Captura para transiciones
├── services/
│   ├── creacut-service.ts          Única puerta hacia Electron
│   ├── gallery-layout.ts           Datos de la galería
│   ├── preview-navigation.ts       Navegación entre clips
│   ├── preview-timeline.ts         Conversión de tiempos
│   ├── seek-coordinator.ts         Coordinación de saltos
│   ├── slide-status.ts             Estado de diapositivas
│   ├── slide-timing.ts             Límites de tiempo
│   ├── transcript-script-sync.ts   Sincronización de texto
│   ├── transition-preview.ts       Geometría de transición
│   └── visual-effects.ts           Filtros visuales
└── types/editor.ts                 Tipos solo de la interfaz
```

Fuera de esta carpeta:

- `src/main/` controla ventana, archivos, procesos y servidor local de medios.
- `src/preload/` expone una API pequeña y segura.
- `src/shared/contracts.ts` describe los datos que cruzan entre procesos.
- `src/renderer/harness.html` permite revisar visualmente el editor sin abrir
  Electron ni ejecutar Python.

## Responsabilidades principales

### App

`App.tsx` abre, guarda y recupera proyectos; inicia análisis, render y lotes;
mantiene la selección y conecta las respuestas del backend con las vistas. No
dibuja los detalles del timeline.

### Vistas

`WelcomeView` compone la entrada, la galería reciente y el resumen del flujo.
`EditorView` arma la barra superior, recursos, visor, timeline e inspector. Los
separadores usan `usePanelLayout` para recordar tamaños y plegado.

### Panel de recursos

`AssetsPanel` reúne transcripción y guion. Durante la reproducción mantiene
visible el texto activo. `ScriptPanel` muestra las oraciones del guion y permite
saltar a sus tomas.

### Inspector

`InspectorPanel` tiene dos áreas generales:

- **Proyecto:** transición, filtros, chroma, fondo, piel, overlays y audio.
- **Diapositivas:** importación, propuestas y biblioteca.

Cuando se selecciona una región, filtro o diapositiva,
`SelectionInspector` muestra sus propiedades. Para una toma reutiliza
`TakeInspectorTab`. Cada cambio se envía a Python y solo se muestra como
guardado cuando el backend lo valida.

### Visor y timeline

`VideoPreview` reproduce el archivo fuente y usa `usePreviewPlayback` para
saltar el material descartado. `useMediaRect` calcula el área real ocupada por
el video, necesaria para colocar correctamente transiciones y presentador.

`TimelinePanel` muestra controles y pistas. `Timeline.tsx` dibuja el canvas. La
altura de las pistas se calcula en `timelineTracks()` y se comparte con
`TimelineTrackGutter`; no debe fijarse manualmente en CSS.

### Servicios y hooks

Los servicios contienen reglas que no necesitan React. Los hooks encapsulan
comportamientos con estado o acceso al navegador. `creacut-service.ts` es la
única puerta del renderer a `window.creacut`; los componentes no deben llamar
IPC directamente.

## Galería de proyectos

La galería actual es una pila vertical de tarjetas. `useProjectStack` mide la
pila y el navegador fija y escala las tarjetas grandes con `position: sticky` y
una animación ligada al scroll cuando hay espacio suficiente. En pantallas
pequeñas o con reducción de movimiento se muestran de forma normal. Los estilos
viven en `components/welcome/project-portfolio.css`.

Consulta [GALERIA_PROYECTOS.md](GALERIA_PROYECTOS.md).

## Previsualización y render

La previsualización busca responder rápido. Los filtros se aproximan con CSS y
las transiciones usan un fotograma congelado. Chroma, fondo, piel, diapositivas
y presentador pueden solicitar un fotograma procesado en Python. El MP4
exportado sigue siendo el resultado definitivo.

## Dónde agregar código

| Necesidad | Carpeta o archivo |
|---|---|
| Pantalla completa | `views/` |
| Bloque visual | `components/` |
| Propiedad contextual | `components/inspector/` |
| Pieza del armazón | `components/layout/` |
| Comportamiento React con estado | `hooks/` |
| Regla pura del frontend | `services/` |
| Nueva operación de backend | contrato + preload + main + servicio |
| Regla de edición | `../creacut/` |

## Reglas que no deben romperse

- Python continúa siendo la fuente de verdad.
- El renderer no recibe acceso general a Node.js.
- Los paneles administran su propio espacio; la ventana del editor no debe
  convertirse en una página con scroll vertical.
- Las capas sobre el video se anclan al rectángulo visible, no al contenedor.
- Región, filtro y diapositiva mantienen una selección única.
- El banco visual no es código muerto; sirve para revisar el armazón sin backend.

## Instancia única

`src/main/single-instance.ts` impide abrir dos procesos principales sobre la
misma caché. Si CREAcut Beta ya está abierto, una segunda ejecución enfoca la
ventana existente.
