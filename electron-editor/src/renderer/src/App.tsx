import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  AnalysisRequest,
  BatchRequest,
  BridgeStatus,
  EffectFramePreview,
  JobEvent,
  ProjectRenderSettingsPatch,
  ProjectView,
  SlidePage,
  RecentProject,
  RecoveryInfo,
  TimelineMedia,
  VisualEffectKind,
  VisualEffectRange
} from '../../shared/contracts'
import { CreateProjectDialog, JobDialog } from './Dialogs'
import type { PresenterBox } from './components/SlidePresenterHandle'
import { BatchDialog } from './components/batch/BatchDialog'
import { usePanelLayout } from './hooks/usePanelLayout'
import { usePreviewPlayback } from './hooks/usePreviewPlayback'
import { useSceneTransition } from './hooks/useSceneTransition'
import { cn } from './lib/utils'
import { creacutService } from './services/creacut-service'
import { recoveryErrorMessage } from './services/recovery-error'
import {
  scriptSegmentForTranscript,
  transcriptIndexAtTime
} from './services/transcript-script-sync'
import type { LeftTab, ThemeMode } from './types/editor'
import { EditorView } from './views/EditorView'
import { WelcomeView } from './views/WelcomeView'

export function App(): React.JSX.Element {
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus | null>(null)
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>([])
  const [recovery, setRecovery] = useState<RecoveryInfo | null>(null)
  const [project, setProject] = useState<ProjectView | null>(null)
  const [timelineMedia, setTimelineMedia] = useState<TimelineMedia | null>(null)
  const [effectFramePreview, setEffectFramePreview] = useState<EffectFramePreview | null>(null)
  const [mediaLoading, setMediaLoading] = useState(false)
  const mediaGeneration = useRef(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [leftTab, setLeftTab] = useState<LeftTab>('transcript')
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null)
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null)
  const [selectedEffectId, setSelectedEffectId] = useState<string | null>(null)
  const [selectedSlideId, setSelectedSlideId] = useState<string | null>(null)
  const [pixelsPerSecond, setPixelsPerSecond] = useState(34)
  const [showCreate, setShowCreate] = useState(false)
  const [showBatch, setShowBatch] = useState(false)
  const [activeJob, setActiveJob] = useState<JobEvent | null>(null)
  const [jobLogs, setJobLogs] = useState<string[]>([])
  const [theme, setTheme] = useState<ThemeMode>(() =>
    window.localStorage.getItem('creacut-theme') === 'light' ? 'light' : 'dark'
  )
  const layout = usePanelLayout()
  const playback = usePreviewPlayback({ project, onError: setError, onSeekSource: selectRegionAtTime })

  function selectRegionAtTime(timeS: number): void {
    const regions = project?.timeline.regions ?? []
    const region = regions.find((item, index) =>
      item.startS <= timeS &&
      (timeS < item.endS || (index === regions.length - 1 && timeS === item.endS))
    )
    setSelectedRegionId(region?.id ?? null)
    setEffectFramePreview(null)
  }

  // Selección única: visor, línea de tiempo e inspector miran siempre al mismo
  // elemento. Solo un clic explícito sobre una región cancela una diapositiva
  // o un filtro seleccionados -- mover el cabezal, no: `selectRegionAtTime`
  // sigue la reproducción decenas de veces por segundo y borrar la selección
  // con cada fotograma vaciaría el inspector mientras se reproduce.
  function selectRegion(regionId: string): void {
    setSelectedRegionId(regionId)
    setSelectedSlideId(null)
    setSelectedEffectId(null)
  }

  function selectSlide(slideId: string): void {
    setSelectedSlideId(slideId)
    setSelectedEffectId(null)
  }

  function selectEffect(effectId: string): void {
    setSelectedEffectId(effectId)
    setSelectedSlideId(null)
  }

  /** Desplazamiento del cabezal por teclado, en el reloj que esté activo. */
  function nudgePlayhead(deltaS: number): void {
    if (!project) return
    if (playback.previewMode === 'preview') {
      playback.seekEdit(Math.max(0, Math.min(project.preview.durationS, (playback.editTimeS ?? 0) + deltaS)))
      return
    }
    playback.seekFromTimeline(
      Math.max(0, Math.min(project.timeline.durationS, playback.sourceTimeS + deltaS))
    )
  }

  // Cambio de pantalla diferido: la bienvenida y el editor no comparten ningun
  // elemento, asi que sustituir una por otra en un fotograma deja al usuario
  // sin saber que ha pasado. `useSceneTransition` retiene el cambio hasta que
  // la pantalla saliente termina su animacion.
  const { scene, leaving, wrapRef } = useSceneTransition(project ? 'editor' : 'welcome')

  // Durante la salida del editor el proyecto ya vale null (lo ha limpiado
  // `exitProject`), pero el editor sigue en pantalla desvaneciendose: necesita
  // los ultimos datos validos para poder pintarse esos ~260ms.
  const lastProject = useRef<ProjectView | null>(null)
  if (project) lastProject.current = project
  const visibleProject = project ?? lastProject.current

  const selectedSegment = useMemo(
    () => project?.project.segments.find((item) => item.id === selectedSegmentId) ?? null,
    [project, selectedSegmentId]
  )
  const selectedRegion = useMemo(
    () => project?.timeline.regions.find((item) => item.id === selectedRegionId) ?? null,
    [project, selectedRegionId]
  )
  const activeTranscriptIndex = useMemo(
    () => project
      ? transcriptIndexAtTime(project.project.transcript.segments, playback.sourceTimeS)
      : null,
    [project, playback.sourceTimeS]
  )
  const activeScriptSegmentId = useMemo(
    () => project
      ? scriptSegmentForTranscript(project, activeTranscriptIndex)?.id ?? null
      : null,
    [project, activeTranscriptIndex]
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem('creacut-theme', theme)
  }, [theme])

  useEffect(() => {
    void Promise.all([
      creacutService.bridgeStatus().then(setBridgeStatus),
      creacutService.recentProjects().then(setRecentProjects),
      creacutService.recoveryInfo().then(setRecovery)
    ]).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))

    creacutService.onJobEvent((event) => {
      setActiveJob((current) => current?.jobId === event.jobId ? { ...current, ...event } : event)
      if (event.kind === 'progress' && event.message) {
        setJobLogs((current) => [...current, event.message!].slice(-240))
      }
      if (event.kind === 'device' && event.label) {
        setJobLogs((current) => [...current, `Dispositivo Whisper: ${event.label}`].slice(-240))
      }
      if (event.kind === 'completed' && event.result?.projectView) {
        acceptNewProject(event.result.projectView)
        setShowCreate(false)
      }
      if (event.kind === 'failed' && event.error) setError(event.error)
    })
  }, [])

  async function hydrateTimelineMedia(generation: number): Promise<void> {
    if (generation !== mediaGeneration.current) return
    setMediaLoading(true)
    try {
      const media = await creacutService.loadTimelineMedia(14, 1000)
      if (generation === mediaGeneration.current) setTimelineMedia(media)
    } catch (reason) {
      if (generation !== mediaGeneration.current) return
      setTimelineMedia({
        thumbnails: [],
        waveform: [],
        warning: reason instanceof Error ? reason.message : String(reason)
      })
    } finally {
      if (generation === mediaGeneration.current) setMediaLoading(false)
    }
  }

  function acceptNewProject(nextProject: ProjectView): void {
    const generation = ++mediaGeneration.current
    playback.reset()
    setProject(nextProject)
    setTimelineMedia(null)
    setEffectFramePreview(null)
    setSelectedSegmentId(nextProject.project.segments[0]?.id ?? null)
    setSelectedRegionId(nextProject.timeline.regions[0]?.id ?? null)
    setSelectedEffectId(null)
    setSelectedSlideId(null)
    setError(null)
    setRecovery(null)
    void creacutService.recentProjects().then(setRecentProjects)
    setMediaLoading(false)
    if (nextProject.sourceExists) void hydrateTimelineMedia(generation)
  }

  function acceptEdit(nextProject: ProjectView): void {
    setProject(nextProject)
    setEffectFramePreview(null)
    const region = nextProject.timeline.regions.find(
      (item, index) =>
        item.startS <= playback.sourceTimeS &&
        (playback.sourceTimeS < item.endS || index === nextProject.timeline.regions.length - 1)
    )
    setSelectedRegionId((current) =>
      nextProject.timeline.regions.some((item) => item.id === current) ? current : region?.id ?? null
    )
    setSelectedEffectId((current) => current && nextProject.effectRanges.some((item) => item.id === current) ? current : null)
    setSelectedSlideId((current) => current && nextProject.slides?.pages.some((item) => item.id === current) ? current : null)
  }

  async function openProject(): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      const result = await creacutService.openProject()
      if (result) acceptNewProject(result)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      if (message !== 'Apertura cancelada') setError(message)
    } finally {
      setBusy(false)
    }
  }

  async function openProjectPath(path: string): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      acceptNewProject(await creacutService.openProjectPath(path))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function restoreRecovery(): Promise<void> {
    setBusy(true)
    try {
      const result = await creacutService.restoreRecovery()
      if (result) acceptNewProject(result)
    } catch (reason) {
      setRecovery(null)
      setError(recoveryErrorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  async function locateMedia(): Promise<void> {
    setBusy(true)
    try {
      const result = await creacutService.locateMedia()
      if (result) acceptNewProject(result)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function projectAction(action: () => Promise<ProjectView>): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      acceptEdit(await action())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function pickBackgroundImage(): Promise<void> {
    try {
      const selected = await creacutService.pickPath('image')
      if (selected) {
        await projectAction(() => creacutService.updateRenderSettings({ backgroundImage: selected }))
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  async function importSlides(kind: 'slides' | 'directory'): Promise<void> {
    try {
      const selected = await creacutService.pickPath(kind)
      if (selected) await projectAction(() => creacutService.importSlideSource(selected))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function removeSlides(): void {
    void projectAction(() => creacutService.removeSlideSource())
  }

  function recommendSlides(): void {
    void projectAction(() => creacutService.recommendSlides())
  }

  function acceptSlideRecommendations(): void {
    void projectAction(() => creacutService.acceptSlideRecommendations())
  }

  function updateSlidePage(pageId: string, patch: Partial<Pick<SlidePage, 'startS' | 'endS' | 'enabled' | 'x' | 'y' | 'speakerWidth' | 'heightFraction'>>): void {
    void projectAction(() => creacutService.updateSlidePage(pageId, patch))
  }

  // "Agregar a la línea de tiempo" antes de correr el análisis (spec: debe
  // ser posible sin haber ejecutado "Analizar y proponer" todavía). Sin una
  // recomendación previa no hay start/end propuestos, así que se ubica junto
  // al playhead con una duración por defecto, igual que addEffectRange.
  function addSlideToTimeline(pageId: string): void {
    if (!project) return
    const page = project.slides?.pages.find((item) => item.id === pageId)
    if (!page) return
    const duration = project.timeline.durationS
    const defaultLength = 5
    const fallbackStart = Math.max(0, Math.min(duration - defaultLength, playback.sourceTimeS))
    const startS = page.startS ?? page.recommendedStartS ?? fallbackStart
    const endS = page.endS ?? page.recommendedEndS ?? Math.min(duration, startS + defaultLength)
    void projectAction(async () => {
      const next = await creacutService.updateSlidePage(pageId, {
        startS: Math.max(0, startS),
        endS: Math.max(Math.max(0, startS) + 0.5, endS),
        enabled: true
      })
      selectSlide(pageId)
      return next
    })
  }

  // Arrastrar o redimensionar al presentador sobre la vista previa de una
  // diapositiva. Mover (x/y) no cambia el recorte del presentador -- solo
  // dónde se dibuja en pantalla, y eso ya se recalcula solo desde
  // `project.slides` en cada render -- así que no hace falta pedirle nada
  // más a Python ni limpiar `effectFramePreview` (por eso no usa
  // `acceptEdit`). Redimensionar (speakerWidth/heightFraction) sí cambia el
  // tamaño real del PNG recortado, así que ese caso vuelve a pedirlo.
  async function repositionSlidePresenter(pageId: string, box: PresenterBox): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      const currentPage = project?.slides?.pages.find((page) => page.id === pageId)
      const sizeChanged =
        !currentPage ||
        Math.abs(currentPage.speakerWidth - box.speakerWidth) > 0.001 ||
        Math.abs(currentPage.heightFraction - box.heightFraction) > 0.001
      const next = await creacutService.updateSlidePage(pageId, box)
      setProject(next)
      if (sizeChanged) {
        setEffectFramePreview(await creacutService.previewEffectsFrame(playback.sourceTimeS))
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  function updateRenderSettings(patch: ProjectRenderSettingsPatch): void {
    void projectAction(() => creacutService.updateRenderSettings(patch))
  }

  function addEffectRange(kind: VisualEffectKind): void {
    if (!project) return
    const duration = project.timeline.durationS
    const endS = Math.min(duration, playback.sourceTimeS + 5)
    const startS = endS - playback.sourceTimeS >= 0.1
      ? playback.sourceTimeS
      : Math.max(0, duration - 5)
    void projectAction(async () => {
      const existing = new Set(project.effectRanges.map((item) => item.id))
      const next = await creacutService.addEffectRange(kind, startS, Math.max(startS + 0.1, endS))
      const created = next.effectRanges.find((item) => !existing.has(item.id))?.id ?? null
      if (created) selectEffect(created)
      return next
    })
  }

  function updateEffectRange(
    effectId: string,
    patch: Partial<Pick<VisualEffectRange, 'kind' | 'startS' | 'endS'>>
  ): void {
    void projectAction(() => creacutService.updateEffectRange(effectId, patch))
  }

  function deleteEffectRange(effectId: string): void {
    setSelectedEffectId(null)
    void projectAction(() => creacutService.deleteEffectRange(effectId))
  }

  async function previewEffectsFrame(): Promise<void> {
    setBusy(true)
    setError(null)
    playback.videoRef.current?.pause()
    try {
      setEffectFramePreview(await creacutService.previewEffectsFrame(playback.sourceTimeS))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function exitProject(): Promise<void> {
    setBusy(true)
    setError(null)
    try {
      if (!(await creacutService.closeProject())) return
      mediaGeneration.current += 1
      setMediaLoading(false)
      playback.reset()
      setProject(null)
      setTimelineMedia(null)
      setEffectFramePreview(null)
      setSelectedSegmentId(null)
      setSelectedRegionId(null)
      setSelectedEffectId(null)
      setSelectedSlideId(null)
      setRecovery(null)
      setRecentProjects(await creacutService.recentProjects())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function saveProject(saveAs = false): Promise<void> {
    setBusy(true)
    try {
      const result = await creacutService.saveProject(saveAs)
      if (result) acceptEdit(result)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function startAnalysis(request: AnalysisRequest): Promise<void> {
    setJobLogs([])
    try {
      const jobId = await creacutService.startAnalysis(request)
      setActiveJob({ jobId, jobKind: 'analysis', kind: 'started' })
      setShowCreate(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  async function startRender(): Promise<void> {
    setJobLogs([])
    try {
      const jobId = await creacutService.startRender()
      if (jobId) setActiveJob({ jobId, jobKind: 'render', kind: 'started' })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  async function startBatch(request: BatchRequest): Promise<void> {
    setJobLogs([])
    try {
      const jobId = await creacutService.startBatch(request)
      setActiveJob({ jobId, jobKind: 'batch', kind: 'started' })
      setShowBatch(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function selectTranscript(index: number): void {
    if (!project) return
    setEffectFramePreview(null)
    const item = project.project.transcript.segments[index]
    if (!item) return
    const segment = scriptSegmentForTranscript(project, index)
    if (segment) setSelectedSegmentId(segment.id)
    const region = project.timeline.regions.find(
      (candidate, position) =>
        candidate.startS <= item.start &&
        (item.start < candidate.endS ||
          (position === project.timeline.regions.length - 1 && item.start === candidate.endS))
    )
    setSelectedRegionId(region?.id ?? null)
    playback.seekToSelection(item.start)
  }

  function selectSegment(segmentId: string): void {
    setEffectFramePreview(null)
    setSelectedSegmentId(segmentId)
    const segment = project?.project.segments.find((item) => item.id === segmentId)
    if (segment?.source_start_s !== null && segment?.source_start_s !== undefined) {
      playback.seekToSelection(segment.source_start_s)
    }
  }

  useEffect(() => {
    const handler = (event: KeyboardEvent): void => {
      const target = event.target as HTMLElement | null
      if (target?.matches('input, textarea, select')) return
      const command = event.ctrlKey || event.metaKey
      if (command && event.key.toLowerCase() === 'o') {
        event.preventDefault()
        void openProject()
      } else if (command && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void saveProject(event.shiftKey)
      } else if (command && event.key.toLowerCase() === 'e') {
        event.preventDefault()
        void startRender()
      } else if (command && event.key.toLowerCase() === 'z' && project) {
        event.preventDefault()
        void projectAction(event.shiftKey ? creacutService.redoTimeline : creacutService.undoTimeline)
      } else if (command && event.altKey && event.key.toLowerCase() === 'b') {
        event.preventDefault()
        layout.toggle('right')
      } else if (command && event.key.toLowerCase() === 'b') {
        event.preventDefault()
        layout.toggle('left')
      } else if (command && event.key.toLowerCase() === 'j') {
        event.preventDefault()
        layout.toggle('timeline')
      } else if (event.code === 'Space' && project) {
        event.preventDefault()
        void playback.togglePlayback()
      } else if (project && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
        // Paso fino con Shift; un segundo en seco es demasiado grueso para
        // ajustar el principio de una frase.
        event.preventDefault()
        const step = event.shiftKey ? 0.1 : 1
        nudgePlayhead(event.key === 'ArrowLeft' ? -step : step)
      } else if (project && event.key === 'Home') {
        event.preventDefault()
        nudgePlayhead(-Number.MAX_SAFE_INTEGER)
      } else if (project && event.key === 'End') {
        event.preventDefault()
        nudgePlayhead(Number.MAX_SAFE_INTEGER)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [project, playback.previewMode, playback.sourceTimeS, playback.editTimeS, layout])

  const dialogs = (
    <>
      {showCreate && <CreateProjectDialog onClose={() => setShowCreate(false)} onStart={startAnalysis} />}
      {showBatch && <BatchDialog onClose={() => setShowBatch(false)} onStart={startBatch} />}
      {activeJob && (
        <JobDialog
          event={activeJob}
          logs={jobLogs}
          onClose={() => setActiveJob(null)}
          onCancel={() => creacutService.cancelJob(activeJob.jobId).then(() => undefined)}
          onOpenProject={openProjectPath}
        />
      )}
    </>
  )

  if (scene === 'welcome') {
    return (
      <>
        <div ref={wrapRef} className={cn('h-full w-full', leaving && 'scene-leave')}>
        <WelcomeView
          bridgeStatus={bridgeStatus}
          recentProjects={recentProjects}
          recovery={recovery}
          busy={busy}
          error={error}
          theme={theme}
          onToggleTheme={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')}
          onNewProject={() => setShowCreate(true)}
          onOpenProject={() => void openProject()}
          onOpenProjectPath={openProjectPath}
          onOpenBatch={() => setShowBatch(true)}
          onRestoreRecovery={() => void restoreRecovery()}
        />
        </div>
        {dialogs}
      </>
    )
  }

  // `scene === 'editor'` solo se alcanza tras haber abierto un proyecto, de
  // modo que `visibleProject` no puede ser null aqui; la comprobacion existe
  // para que TypeScript lo sepa.
  if (!visibleProject) return <></>

  return (
    <>
      <div ref={wrapRef} className={cn('h-full w-full', leaving && 'scene-leave')}>
      <EditorView
        project={visibleProject}
        playback={playback}
        layout={layout}
        selectedSegment={selectedSegment}
        selectedRegion={selectedRegion}
        selectedSegmentId={selectedSegmentId}
        selectedRegionId={selectedRegionId}
        activeTranscriptIndex={activeTranscriptIndex}
        activeScriptSegmentId={activeScriptSegmentId}
        timelineMedia={timelineMedia}
        mediaLoading={mediaLoading}
        busy={busy}
        error={error}
        leftTab={leftTab}
        theme={theme}
        pixelsPerSecond={pixelsPerSecond}
        effectFramePreview={effectFramePreview}
        selectedEffectId={selectedEffectId}
        selectedSlideId={selectedSlideId}
        onDismissError={() => setError(null)}
        onLeftTabChange={setLeftTab}
        onThemeToggle={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')}
        onPixelsPerSecondChange={setPixelsPerSecond}
        onSelectSegment={selectSegment}
        onSelectRegion={selectRegion}
        onSelectTranscript={selectTranscript}
        onLocateMedia={() => void locateMedia()}
        onSave={(saveAs) => void saveProject(saveAs)}
        onNewProject={() => setShowCreate(true)}
        onExport={() => void startRender()}
        onBatch={() => setShowBatch(true)}
        onOpen={() => void openProject()}
        onExitProject={() => void exitProject()}
        onKeepRegion={() => selectedRegion && void projectAction(() => creacutService.markRegion(selectedRegion.id, true))}
        onDiscardRegion={() => selectedRegion && void projectAction(() => creacutService.markRegion(selectedRegion.id, false))}
        onRestoreRegion={() => selectedRegion && void projectAction(() => creacutService.restoreRegion(selectedRegion.id))}
        onSplit={() => void projectAction(() => creacutService.splitTimeline(playback.sourceTimeS))}
        onUndo={() => void projectAction(creacutService.undoTimeline)}
        onRedo={() => void projectAction(creacutService.redoTimeline)}
        onMoveBoundary={(oldTime, newTime) => void projectAction(() => creacutService.moveTimelineBoundary(oldTime, newTime))}
        onSelectCandidate={(segmentId, candidateId) => void projectAction(() => creacutService.selectCandidate(segmentId, candidateId))}
        onRestoreCandidate={(segmentId) => void projectAction(() => creacutService.restoreCandidate(segmentId))}
        onUpdateRenderSettings={updateRenderSettings}
        onPickBackground={() => void pickBackgroundImage()}
        onPreviewEffects={() => void previewEffectsFrame()}
        onPickSlides={() => void importSlides('slides')}
        onPickSlidesFolder={() => void importSlides('directory')}
        onRemoveSlides={removeSlides}
        onRecommendSlides={recommendSlides}
        onAcceptSlideRecommendations={acceptSlideRecommendations}
        onUpdateSlidePage={updateSlidePage}
        onSelectSlide={selectSlide}
        onAddSlideToTimeline={addSlideToTimeline}
        onRepositionSlidePresenter={(pageId, box) => void repositionSlidePresenter(pageId, box)}
        onCloseEffectPreview={() => setEffectFramePreview(null)}
        onAddEffect={addEffectRange}
        onSelectEffect={selectEffect}
        onUpdateEffect={updateEffectRange}
        onDeleteEffect={deleteEffectRange}
      />
      </div>
      {dialogs}
    </>
  )
}
