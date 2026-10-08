import type {
  EditSegment,
  EffectFramePreview,
  ProjectRenderSettingsPatch,
  ProjectView,
  SlidePage,
  TimelineMedia,
  TimelineRegion,
  VisualEffectKind,
  VisualEffectRange
} from '../../../shared/contracts'
import { AssetsPanel } from '../components/AssetsPanel'
import { EditorTopbar } from '../components/EditorTopbar'
import { ErrorToast } from '../components/ErrorToast'
import { InspectorPanel } from '../components/InspectorPanel'
import { PanelDivider } from '../components/layout/PanelDivider'
import type { PresenterBox } from '../components/SlidePresenterHandle'
import { TimelinePanel } from '../components/TimelinePanel'
import { VideoPreview } from '../components/VideoPreview'
import { PANEL_BOUNDS, type PanelLayout } from '../hooks/usePanelLayout'
import type { PreviewPlaybackController } from '../hooks/usePreviewPlayback'
import type { LeftTab, ThemeMode } from '../types/editor'

/**
 * Armazón del editor.
 *
 * El cambio de fondo respecto a la versión anterior es que el armazón ocupa
 * **exactamente** la ventana y ninguna de sus regiones se desplaza en
 * vertical. Antes la columna central era un contenedor con `overflow-y: auto`
 * que apilaba visor y línea de tiempo: en una ventana baja había que
 * desplazarla para llegar a la línea de tiempo, que es el gesto de una página
 * web y no el de un editor.
 *
 * Ahora los tres bordes internos son separadores arrastrables y cada panel se
 * puede plegar; el visor se queda con todo el espacio que sobre, que es lo que
 * lo convierte en el protagonista.
 */
interface EditorViewProps {
  project: ProjectView
  playback: PreviewPlaybackController
  layout: PanelLayout
  selectedSegment: EditSegment | null
  selectedRegion: TimelineRegion | null
  selectedSegmentId: string | null
  selectedRegionId: string | null
  activeTranscriptIndex: number | null
  activeScriptSegmentId: string | null
  timelineMedia: TimelineMedia | null
  mediaLoading: boolean
  busy: boolean
  error: string | null
  leftTab: LeftTab
  theme: ThemeMode
  pixelsPerSecond: number
  effectFramePreview: EffectFramePreview | null
  selectedEffectId: string | null
  selectedSlideId: string | null
  onDismissError: () => void
  onLeftTabChange: (tab: LeftTab) => void
  onThemeToggle: () => void
  onPixelsPerSecondChange: (value: number) => void
  onSelectSegment: (segmentId: string) => void
  onSelectRegion: (regionId: string) => void
  onSelectTranscript: (index: number) => void
  onLocateMedia: () => void
  onSave: (saveAs: boolean) => void
  onNewProject: () => void
  onExport: () => void
  onBatch: () => void
  onOpen: () => void
  onExitProject: () => void
  onKeepRegion: () => void
  onDiscardRegion: () => void
  onRestoreRegion: () => void
  onSplit: () => void
  onUndo: () => void
  onRedo: () => void
  onMoveBoundary: (oldTimeS: number, newTimeS: number) => void
  onSelectCandidate: (segmentId: string, candidateId: string) => void
  onRestoreCandidate: (segmentId: string) => void
  onUpdateRenderSettings: (patch: ProjectRenderSettingsPatch) => void
  onPickBackground: () => void
  onPreviewEffects: () => void
  onPickSlides: () => void
  onPickSlidesFolder: () => void
  onRemoveSlides: () => void
  onRecommendSlides: () => void
  onAcceptSlideRecommendations: () => void
  onUpdateSlidePage: (pageId: string, patch: Partial<Pick<SlidePage, 'startS' | 'endS' | 'enabled' | 'x' | 'y' | 'speakerWidth' | 'heightFraction'>>) => void
  onSelectSlide: (slideId: string) => void
  onAddSlideToTimeline: (pageId: string) => void
  onRepositionSlidePresenter: (pageId: string, box: PresenterBox) => void
  onCloseEffectPreview: () => void
  onAddEffect: (kind: VisualEffectKind) => void
  onSelectEffect: (effectId: string) => void
  onUpdateEffect: (effectId: string, patch: Partial<Pick<VisualEffectRange, 'kind' | 'startS' | 'endS'>>) => void
  onDeleteEffect: (effectId: string) => void
}

/** Alto de la línea de tiempo plegada: solo su barra de herramientas. */
const TIMELINE_COLLAPSED_HEIGHT = 36

export function EditorView(props: EditorViewProps): React.JSX.Element {
  const {
    project,
    playback,
    layout,
    selectedSegment,
    selectedRegion,
    selectedSegmentId,
    selectedRegionId,
    activeTranscriptIndex,
    activeScriptSegmentId,
    timelineMedia,
    mediaLoading,
    busy,
    error,
    leftTab,
    theme,
    pixelsPerSecond,
    effectFramePreview
  } = props

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <EditorTopbar
        className="scene-enter scene-enter--top"
        project={project}
        busy={busy}
        theme={theme}
        collapsed={layout.collapsed}
        onTogglePanel={layout.toggle}
        onToggleTheme={props.onThemeToggle}
        onSave={props.onSave}
        onNewProject={props.onNewProject}
        onExport={props.onExport}
        onBatch={props.onBatch}
        onOpen={props.onOpen}
        onExitProject={props.onExitProject}
      />

      {/* Indicador de trabajo en curso. Es indeterminado a propósito: el
          backend no informa de porcentaje en las operaciones del editor, y una
          barra que avanza sin datos reales sería una mentira. Ocupa el borde
          inferior de la barra superior, así que no reserva espacio ni desplaza
          nada al aparecer. */}
      <div className="relative z-20 h-0">
        {busy && <div className="busy-bar" role="status" aria-label="Operación en curso" />}
      </div>

      <div className="flex min-h-0 flex-1">
        {!layout.collapsed.left && (
          <>
            <AssetsPanel
              className="scene-enter scene-enter--left"
              // El panel conserva su ancho preferido mientras quepa y se
              // encoge hasta su mínimo antes de robarle sitio al visor: en
              // una ventana estrecha, con anchos fijos, el inspector acababa
              // solapando la columna central.
              style={{ width: layout.size.left, minWidth: PANEL_BOUNDS.left.min }}
              project={project}
              activeTranscriptIndex={activeTranscriptIndex}
              activeScriptSegmentId={activeScriptSegmentId}
              selectedSegmentId={selectedSegmentId}
              tab={leftTab}
              onTabChange={props.onLeftTabChange}
              onSelectTranscript={props.onSelectTranscript}
              onSelectSegment={props.onSelectSegment}
            />
            <PanelDivider
              orientation="vertical"
              label="Ancho del panel de material"
              value={{ now: layout.size.left, min: PANEL_BOUNDS.left.min, max: PANEL_BOUNDS.left.max }}
              onResize={(delta) => layout.resize('left', delta)}
              onReset={() => layout.reset('left')}
            />
          </>
        )}

        <main className="relative flex min-h-0 flex-1 flex-col" style={{ minWidth: 360 }}>
          <VideoPreview
            className="scene-enter scene-enter--stage"
            project={project}
            playback={playback}
            effectFramePreview={effectFramePreview}
            busy={busy}
            onLocateMedia={props.onLocateMedia}
            onCloseEffectPreview={props.onCloseEffectPreview}
            onRepositionSlidePresenter={props.onRepositionSlidePresenter}
          />

          <PanelDivider
            orientation="horizontal"
            label="Alto de la línea de tiempo"
            value={{ now: layout.size.timeline, min: PANEL_BOUNDS.timeline.min, max: PANEL_BOUNDS.timeline.max }}
            // Arrastrar hacia arriba agranda la línea de tiempo: el separador
            // es su borde superior, así que el delta va con el signo cambiado.
            onResize={(delta) => layout.resize('timeline', -delta)}
            onReset={() => layout.reset('timeline')}
          />

          <TimelinePanel
            className="scene-enter scene-enter--bottom"
            style={{
              height: layout.collapsed.timeline ? TIMELINE_COLLAPSED_HEIGHT : layout.size.timeline
            }}
            project={project}
            media={timelineMedia}
            mediaLoading={mediaLoading}
            busy={busy}
            sourceTimeS={playback.sourceTimeS}
            editTimeS={playback.editTimeS}
            previewMode={playback.previewMode}
            pixelsPerSecond={pixelsPerSecond}
            selectedRegionId={selectedRegionId}
            selectedRegion={selectedRegion}
            theme={theme}
            onPixelsPerSecondChange={props.onPixelsPerSecondChange}
            onSelectRegion={props.onSelectRegion}
            onSeek={(timeS) => {
              props.onCloseEffectPreview()
              playback.seekFromTimeline(timeS)
            }}
            onSeekEdit={(timeS) => {
              props.onCloseEffectPreview()
              playback.seekEdit(timeS)
            }}
            onMoveBoundary={props.onMoveBoundary}
            onKeepRegion={props.onKeepRegion}
            onDiscardRegion={props.onDiscardRegion}
            onRestoreRegion={props.onRestoreRegion}
            onSplit={props.onSplit}
            onUndo={props.onUndo}
            onRedo={props.onRedo}
            selectedEffectId={props.selectedEffectId}
            onSelectEffect={props.onSelectEffect}
            onUpdateEffectRange={props.onUpdateEffect}
            slidePages={project.slides?.pages ?? []}
            selectedSlideId={props.selectedSlideId}
            onSelectSlide={props.onSelectSlide}
            onUpdateSlideTiming={props.onUpdateSlidePage}
          />

          <ErrorToast message={error} onDismiss={props.onDismissError} />
        </main>

        {!layout.collapsed.right && (
          <>
            <PanelDivider
              orientation="vertical"
              label="Ancho del inspector"
              value={{ now: layout.size.right, min: PANEL_BOUNDS.right.min, max: PANEL_BOUNDS.right.max }}
              onResize={(delta) => layout.resize('right', -delta)}
              onReset={() => layout.reset('right')}
            />
            <InspectorPanel
              className="scene-enter scene-enter--right"
              style={{ width: layout.size.right, minWidth: PANEL_BOUNDS.right.min }}
              project={project}
              selectedSegment={selectedSegment}
              selectedSegmentId={selectedSegmentId}
              busy={busy}
              onSelectSegment={props.onSelectSegment}
              onSeekCandidate={(timeS) => {
                props.onCloseEffectPreview()
                playback.seekToSelection(timeS)
              }}
              onSelectCandidate={props.onSelectCandidate}
              onRestoreCandidate={props.onRestoreCandidate}
              onUpdateRenderSettings={props.onUpdateRenderSettings}
              onPickBackground={props.onPickBackground}
              onPreviewEffects={props.onPreviewEffects}
              selectedSlideId={props.selectedSlideId}
              onUpdateSlidePage={props.onUpdateSlidePage}
              selectedEffectId={props.selectedEffectId}
              sourceTimeS={playback.sourceTimeS}
              onAddEffect={props.onAddEffect}
              onSelectEffect={props.onSelectEffect}
              onUpdateEffect={props.onUpdateEffect}
              onDeleteEffect={props.onDeleteEffect}
              onSelectSlide={props.onSelectSlide}
              onPickSlides={props.onPickSlides}
              onPickSlidesFolder={props.onPickSlidesFolder}
              onRemoveSlides={props.onRemoveSlides}
              onRecommendSlides={props.onRecommendSlides}
              onAcceptSlideRecommendations={props.onAcceptSlideRecommendations}
              onAddSlideToTimeline={props.onAddSlideToTimeline}
            />
          </>
        )}
      </div>
    </div>
  )
}
