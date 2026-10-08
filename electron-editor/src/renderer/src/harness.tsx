/**
 * Banco de pruebas visual del editor (solo desarrollo).
 *
 * Monta `EditorView` con un proyecto de mentira y un controlador de
 * reproducción falso, para poder revisar el armazón, los separadores, la
 * línea de tiempo y el inspector en un navegador, sin backend Python ni
 * Electron. No entra en el `build`: `electron-vite` compila `index.html`, no
 * este archivo.
 *
 *   npx vite --config vite.harness.config.ts
 */
import { useMemo, useRef, useState } from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/inter'
import type {
  EditSegment,
  ProjectView,
  SlidePage,
  TimelineMedia,
  TimelineRegion
} from '../../shared/contracts'
import { TooltipProvider } from './components/ui/tooltip'
import { usePanelLayout } from './hooks/usePanelLayout'
import type { PreviewPlaybackController } from './hooks/usePreviewPlayback'
import type { LeftTab, PreviewMode, ThemeMode } from './types/editor'
import { EditorView } from './views/EditorView'
import './styles.css'

const DURATION_S = 720

function regions(): TimelineRegion[] {
  const cuts = [0, 42, 96, 158, 214, 275, 340, 405, 468, 540, 611, 672, DURATION_S]
  return cuts.slice(0, -1).map((startS, index) => ({
    id: `region-${index}`,
    startS,
    endS: cuts[index + 1],
    automaticKeep: index % 3 !== 1,
    keep: index % 3 !== 1,
    origin: 'auto',
    linkedSegmentIds: []
  }))
}

function segments(): EditSegment[] {
  const texts = [
    'El marco conceptual organiza las ideas centrales del curso.',
    'Cada categoría se apoya en la evidencia recogida en campo.',
    'La tercera parte conecta la teoría con el ejercicio práctico.',
    'Cerramos con las preguntas que quedan abiertas.'
  ]
  return texts.map((script_text, index) => ({
    id: `segment-${index}`,
    paragraph_idx: Math.floor(index / 2),
    sentence_idx: index % 2,
    script_text,
    candidates: [0, 1].map((take) => ({
      id: `segment-${index}-take-${take}`,
      source_start_s: 40 * index + 12 * take,
      source_end_s: 40 * index + 12 * take + 9.5,
      duration_s: 9.5,
      score: 0.91 - take * 0.18,
      transcript_text: script_text,
      refinements: []
    })),
    selected_candidate_id: `segment-${index}-take-0`,
    source_start_s: 40 * index,
    source_end_s: 40 * index + 9.5,
    automatic_selection: {
      recommended_candidate_id: `segment-${index}-take-0`,
      selection_reason: 'mejor_puntaje'
    }
  }))
}

function slidePages(): SlidePage[] {
  return [0, 1, 2, 3, 4, 5].map((index) => ({
    id: `slide-${index}`,
    index,
    imagePath: '',
    imageUrl: null,
    thumbnailPath: '',
    thumbnailUrl: null,
    width: 1920,
    height: 1080,
    text: `Diapositiva ${index + 1}`,
    recommendedStartS: 60 * index + 10,
    recommendedEndS: 60 * index + 48,
    recommendationScore: 0.4 - index * 0.05,
    recommendationReason: 'Coincide con el vocabulario del bloque siguiente.',
    recommendationMode: index % 2 === 0 ? 'lexical-match' : 'ordered-fallback',
    startS: index < 4 ? 60 * index + 10 : null,
    endS: index < 4 ? 60 * index + 48 : null,
    enabled: index < 3,
    x: 0.62,
    y: 0.24,
    speakerWidth: 0.3,
    heightFraction: 0.68,
    cropX: 0,
    cropY: 0,
    cropWidth: 1,
    cropHeight: 1
  }))
}

const PROJECT: ProjectView = {
  projectPath: 'C:/Users/ajpp2/Documents/CREA/VP/marco-conceptual.creacut.json',
  projectName: 'marco-conceptual',
  sourcePath: 'C:/Users/ajpp2/Documents/CREA/VP/marco-conceptual.mp4',
  sourceExists: true,
  mediaUrl: null,
  scriptText: null,
  scriptError: null,
  dirty: true,
  canUndo: true,
  canRedo: false,
  project: {
    kind: 'creacut-project',
    schema_version: 3,
    project_id: 'demo',
    source: { path: 'marco-conceptual.mp4', duration_s: DURATION_S },
    script: { path: 'guion.md' },
    transcript: {
      text: '',
      segments: Array.from({ length: 60 }, (_, index) => ({
        start: index * 12,
        end: index * 12 + 11,
        text: `Fragmento ${index + 1} de la transcripción automática del video de clase.`
      }))
    },
    segments: segments(),
    extensions: {}
  },
  timeline: {
    durationS: DURATION_S,
    regions: regions(),
    cutPointsS: [42, 96, 158, 214, 275, 340, 405, 468, 540, 611, 672]
  },
  preview: { durationS: 470, clips: [], cutPointsS: [42, 96, 158] },
  renderSettings: {
    transitionType: 'dissolve',
    crossfadeS: 0.25,
    chromaEnabled: true,
    backgroundImage: null,
    skinCorrectionEnabled: true,
    skinCorrectionStrength: 0.6,
    listOverlaysEnabled: true,
    termOverlaysEnabled: false,
    boldCardsEnabled: true,
    normalizeAudio: true
  },
  effectRanges: [
    { id: 'fx-1', kind: 'cinematic', startS: 30, endS: 88 },
    { id: 'fx-2', kind: 'warm', startS: 220, endS: 268 },
    { id: 'fx-3', kind: 'vintage', startS: 430, endS: 512 }
  ],
  slides: {
    sourcePath: 'C:/Users/ajpp2/Documents/CREA/VP/marco.pptx',
    sourceKind: 'pptx',
    renderer: 'powerpoint',
    importedAtUtc: new Date().toISOString(),
    pages: slidePages()
  }
}

const MEDIA: TimelineMedia = {
  warning: null,
  thumbnails: [],
  waveform: Array.from({ length: 900 }, (_, index) =>
    Math.abs(Math.sin(index / 9) * 0.55 + Math.sin(index / 2.3) * 0.3)
  )
}

function Harness(): React.JSX.Element {
  const layout = usePanelLayout()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [theme, setTheme] = useState<ThemeMode>('dark')
  const [leftTab, setLeftTab] = useState<LeftTab>('transcript')
  const [mode, setMode] = useState<PreviewMode>('source')
  const [timeS, setTimeS] = useState(126)
  const [regionId, setRegionId] = useState<string | null>('region-2')
  const [slideId, setSlideId] = useState<string | null>(null)
  const [effectId, setEffectId] = useState<string | null>(null)
  const [segmentId, setSegmentId] = useState<string | null>('segment-1')
  const [error, setError] = useState<string | null>(null)
  const [pps, setPps] = useState(34)

  document.documentElement.dataset.theme = theme

  const playback: PreviewPlaybackController = useMemo(
    () => ({
      videoRef,
      previewMode: mode,
      playing: false,
      sourceTimeS: timeS,
      editTimeS: timeS * 0.8,
      reset: () => undefined,
      seekSource: setTimeS,
      seekEdit: (value) => setTimeS(value / 0.8),
      seekToSelection: setTimeS,
      seekFromTimeline: setTimeS,
      changeMode: setMode,
      togglePlayback: async () => undefined,
      jump: () => undefined,
      onLoadedMetadata: () => undefined,
      onSeeked: () => undefined,
      onPlaying: () => undefined,
      onPause: () => undefined,
      onTimeUpdate: () => undefined,
      onError: () => undefined
    }),
    [mode, timeS]
  )

  const selectedRegion = PROJECT.timeline.regions.find((item) => item.id === regionId) ?? null
  const selectedSegment = PROJECT.project.segments.find((item) => item.id === segmentId) ?? null
  const noop = (): void => undefined

  return (
    <EditorView
      project={PROJECT}
      playback={playback}
      layout={layout}
      selectedSegment={selectedSegment}
      selectedRegion={selectedRegion}
      selectedSegmentId={segmentId}
      selectedRegionId={regionId}
      activeTranscriptIndex={Math.floor(timeS / 12)}
      activeScriptSegmentId={segmentId}
      timelineMedia={MEDIA}
      mediaLoading={false}
      busy={false}
      error={error}
      leftTab={leftTab}
      theme={theme}
      pixelsPerSecond={pps}
      effectFramePreview={null}
      selectedEffectId={effectId}
      selectedSlideId={slideId}
      onDismissError={() => setError(null)}
      onLeftTabChange={setLeftTab}
      onThemeToggle={() => setTheme((value) => (value === 'dark' ? 'light' : 'dark'))}
      onPixelsPerSecondChange={setPps}
      onSelectSegment={setSegmentId}
      onSelectRegion={(id) => {
        setRegionId(id)
        setSlideId(null)
        setEffectId(null)
      }}
      onSelectTranscript={(index) => setTimeS(index * 12)}
      onLocateMedia={noop}
      onSave={noop}
      onNewProject={noop}
      onExport={() => setError('Ejemplo de aviso: el render necesita Chroma activado para las diapositivas activas.\nC:/Users/ajpp2/Documents/CREA/VP/marco-conceptual.creacut.json')}
      onBatch={noop}
      onOpen={noop}
      onExitProject={noop}
      onKeepRegion={noop}
      onDiscardRegion={noop}
      onRestoreRegion={noop}
      onSplit={noop}
      onUndo={noop}
      onRedo={noop}
      onMoveBoundary={noop}
      onSelectCandidate={noop}
      onRestoreCandidate={noop}
      onUpdateRenderSettings={noop}
      onPickBackground={noop}
      onPreviewEffects={noop}
      onPickSlides={noop}
      onPickSlidesFolder={noop}
      onRemoveSlides={noop}
      onRecommendSlides={noop}
      onAcceptSlideRecommendations={noop}
      onUpdateSlidePage={noop}
      onSelectSlide={(id) => {
        setSlideId(id)
        setEffectId(null)
      }}
      onAddSlideToTimeline={noop}
      onRepositionSlidePresenter={noop}
      onCloseEffectPreview={noop}
      onAddEffect={noop}
      onSelectEffect={(id) => {
        setEffectId(id)
        setSlideId(null)
      }}
      onUpdateEffect={noop}
      onDeleteEffect={noop}
    />
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <TooltipProvider delayDuration={280} skipDelayDuration={400}>
    <Harness />
  </TooltipProvider>
)
