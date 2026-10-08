import { useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, FileVideo2, LocateFixed, Pause, Play, X } from 'lucide-react'
import type { EffectFramePreview, ProjectView } from '../../../shared/contracts'
import type { PreviewPlaybackController } from '../hooks/usePreviewPlayback'
import type { PreviewMode } from '../types/editor'
import { formatTime } from '../format'
import { activeVisualEffects, visualEffectCss, visualEffectLabel } from '../services/visual-effects'
import { useMediaRect } from '../hooks/useMediaRect'
import { useTransitionPreview } from '../hooks/useTransitionPreview'
import { SlidePresenterHandle, type PresenterBox } from './SlidePresenterHandle'
import { TransitionOverlay } from './TransitionOverlay'
import { Button } from './ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { cn } from '../lib/utils'
import { SegmentedList, SegmentedTrigger, Tabs } from './ui/tabs'

interface VideoPreviewProps {
  className?: string
  project: ProjectView
  playback: PreviewPlaybackController
  effectFramePreview: EffectFramePreview | null
  busy: boolean
  onLocateMedia: () => void
  onCloseEffectPreview: () => void
  onRepositionSlidePresenter: (pageId: string, box: PresenterBox) => void
}

const MODE_HINT: Record<PreviewMode, string> = {
  source: 'Reloj del video fuente',
  edit: 'Navegación entre partes editadas',
  preview: 'Resultado final, corte a corte'
}

const MODE_BADGE: Record<PreviewMode, string> = {
  source: 'ORIGINAL',
  edit: 'PROPUESTA',
  preview: 'PREVISUALIZACIÓN'
}

/**
 * Visor.
 *
 * Reparto del espacio
 * -------------------
 * El escenario ocupa **todo** el alto libre de la columna central en lugar de
 * derivar su altura de la proporción del material. Antes el visor medía
 * `ancho / 16:9` y, cuando no cabía, la columna entera se desplazaba en
 * vertical: el gesto de una página web. Ahora la imagen se encaja dentro del
 * espacio disponible y el resto es fondo de escenario.
 *
 * Capas sobre la imagen
 * ---------------------
 * Todo lo que se superpone al vídeo (presentador, etiquetas de modo y efecto,
 * capa congelada de la transición) vive dentro de un marco colocado sobre el
 * **rectángulo real de la imagen**, no sobre el contenedor. Esa es la razón de
 * que el presentador conserve su posición relativa al vídeo cuando se
 * redimensiona un panel: su caja está expresada en fracciones de ese marco.
 *
 * El recorte ocurre en el borde del escenario y no en el del marco, así que
 * los asideros de las esquinas del presentador siguen siendo agarrables cuando
 * la persona toca el borde de la imagen.
 */
export function VideoPreview({
  className,
  project,
  playback,
  effectFramePreview,
  busy,
  onLocateMedia,
  onCloseEffectPreview,
  onRepositionSlidePresenter
}: VideoPreviewProps): React.JSX.Element {
  const stageRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<HTMLDivElement>(null)
  const [mediaAspect, setMediaAspect] = useState<{ source: string | null; ratio: number } | null>(null)
  const [previewAspect, setPreviewAspect] = useState<{ url: string; ratio: number } | null>(null)

  const activeSlidePage = effectFramePreview?.slidePageId
    ? project.slides?.pages.find((page) => page.id === effectFramePreview.slidePageId) ?? null
    : null

  // Una diapositiva compuesta no tiene por qué compartir proporción con la
  // cámara: el marco adopta la del fotograma que se está mostrando, de modo
  // que la imagen nunca se estira y el presentador cae exactamente donde
  // caerá en el render.
  const composedAspect =
    activeSlidePage && effectFramePreview && previewAspect?.url === effectFramePreview.url
      ? previewAspect.ratio
      : null
  const aspectRatio =
    composedAspect ?? (mediaAspect?.source === project.mediaUrl ? mediaAspect.ratio : 16 / 9)
  const mediaRect = useMediaRect(stageRef, aspectRatio)

  const mode = playback.previewMode
  const isSource = mode === 'source'
  // La previsualizacion se mide en tiempo editado; 'edit' sigue usando el
  // reloj y el scrubber del video fuente, como hasta ahora.
  const isPreview = mode === 'preview'
  const previousLabel = 'Parte editada anterior'
  const nextLabel = 'Siguiente parte editada'
  const scrubMaxS = isPreview ? project.preview.durationS : project.timeline.durationS
  const scrubValueS = isPreview ? playback.editTimeS ?? 0 : playback.sourceTimeS
  const activeEffects = activeVisualEffects(project.effectRanges, playback.sourceTimeS)
  // La transicion solo tiene sentido reproduciendo el resultado final: al
  // arrastrar el cabezal el usuario busca un instante, no mira el corte.
  const transition = useTransitionPreview({
    project,
    videoRef: playback.videoRef,
    editTimeS: playback.editTimeS,
    active: isPreview && playback.playing && !effectFramePreview
  })

  return (
    <section className={cn('flex min-h-0 min-w-0 flex-1 flex-col bg-card', className)}>
      <header className="flex h-9 shrink-0 items-center gap-2.5 border-b border-border px-2.5">
        <Tabs value={mode} onValueChange={(value) => playback.changeMode(value as PreviewMode)}>
          <SegmentedList>
            <SegmentedTrigger value="source">Original</SegmentedTrigger>
            <SegmentedTrigger value="edit">Propuesta</SegmentedTrigger>
            <SegmentedTrigger value="preview">Previsualización</SegmentedTrigger>
          </SegmentedList>
        </Tabs>
        <span className="min-w-0 truncate text-[11px] text-muted-foreground">{MODE_HINT[mode]}</span>
        {!effectFramePreview && activeEffects.length > 0 && (
          <span className="ml-auto shrink-0 rounded-full border border-primary/30 bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-primary">
            {activeEffects.map((item) => visualEffectLabel(item.kind)).join(' + ')}
          </span>
        )}
      </header>

      <div
        className="hud-frame group/stage relative isolate min-h-0 flex-1 overflow-hidden bg-video-stage"
        data-video-viewer
        data-playing={playback.playing ? 'true' : 'false'}
      >
        <div className="video-veil pointer-events-none absolute inset-0 z-0" />

        {!project.mediaUrl ? (
          <div className="absolute inset-0 z-[1] flex flex-col items-center justify-center gap-2.5 px-6 text-center text-muted-foreground">
            <FileVideo2 size={40} className="opacity-70" />
            <strong className="text-sm text-foreground">Video fuente no encontrado</strong>
            <span className="max-w-[480px] break-all text-[10px]">
              {project.sourcePath ?? project.project.source.path}
            </span>
            <Button variant="primary" size="sm" className="mt-1" onClick={onLocateMedia}>
              <LocateFixed size={15} /> Ubicar video
            </Button>
          </div>
        ) : null}

        {/* Caja de medida: el marco de imagen se coloca dentro de ella, así que
            queda siempre un margen donde caben los asideros del presentador. */}
        <div ref={stageRef} className="absolute inset-3 z-[1]">
          {mediaRect && (
            <div
              ref={frameRef}
              className="absolute"
              data-video-canvas
              style={{
                left: mediaRect.left,
                top: mediaRect.top,
                width: mediaRect.width,
                height: mediaRect.height
              }}
            >
              {project.mediaUrl && (
                <video
                  className={cn(
                    'absolute inset-0 z-[1] h-full w-full object-contain',
                    effectFramePreview && 'invisible'
                  )}
                  ref={playback.videoRef}
                  src={project.mediaUrl}
                  preload="auto"
                  playsInline
                  style={{
                    filter: visualEffectCss(project.effectRanges, playback.sourceTimeS),
                    // En un deslizamiento los dos clips se mueven a la vez: si solo
                    // se desplazara la capa congelada, se verían las dos imágenes
                    // separadas en mitad del corte.
                    transform: transition.visual?.incoming.transform ?? 'none'
                  }}
                  onLoadedMetadata={(event) => {
                    const video = event.currentTarget
                    if (video.videoWidth > 0 && video.videoHeight > 0) {
                      setMediaAspect({ source: project.mediaUrl, ratio: video.videoWidth / video.videoHeight })
                    }
                    playback.onLoadedMetadata(video)
                  }}
                  onSeeked={(event) => playback.onSeeked(event.currentTarget)}
                  onPlaying={playback.onPlaying}
                  onPause={playback.onPause}
                  onEnded={playback.onPause}
                  onTimeUpdate={(event) => playback.onTimeUpdate(event.currentTarget)}
                  onError={(event) => playback.onError(event.currentTarget)}
                />
              )}

              <TransitionOverlay
                canvasRef={transition.canvasRef}
                visual={transition.visual}
                frame={transition.frame}
              />

              {effectFramePreview && (
                <div className="absolute inset-0 z-[3]">
                  <img
                    src={effectFramePreview.url}
                    onLoad={(event) => {
                      const image = event.currentTarget
                      if (image.naturalWidth > 0 && image.naturalHeight > 0) {
                        setPreviewAspect({
                          url: effectFramePreview.url,
                          ratio: image.naturalWidth / image.naturalHeight
                        })
                      }
                    }}
                    alt={activeSlidePage ? 'Diapositiva compuesta' : 'Fotograma con efectos de render'}
                    // El marco ya adopta la proporción de esta imagen, así que
                    // `fill` y `contain` coinciden: se usa `fill` para que no
                    // queden franjas de medio píxel entre capas.
                    className="h-full w-full object-fill"
                  />
                </div>
              )}

              {activeSlidePage && effectFramePreview?.presenterUrl && (
                <SlidePresenterHandle
                  containerRef={frameRef}
                  presenterUrl={effectFramePreview.presenterUrl}
                  page={activeSlidePage}
                  disabled={busy}
                  onCommit={(box) => onRepositionSlidePresenter(activeSlidePage.id, box)}
                />
              )}

              <span className="stage-chip absolute left-2 top-2 z-[5]">
                <span
                  className={cn('live-dot', !isSource && 'live-dot--brand')}
                  style={isSource ? { background: 'var(--info)' } : undefined}
                />
                {MODE_BADGE[mode]}
              </span>

              {effectFramePreview && (
                <span className="stage-chip absolute right-2 top-2 z-[5]">
                  {activeSlidePage ? `DIAPOSITIVA ${activeSlidePage.index + 1}` : 'EFECTOS'} ·{' '}
                  {formatTime(effectFramePreview.timeS, true)}
                  <button
                    type="button"
                    className="-mr-0.5 rounded-sm p-0.5 transition-colors duration-[var(--dur-hover)] ease-out hover:bg-white/15"
                    aria-label="Cerrar vista de efectos"
                    onClick={onCloseEffectPreview}
                  >
                    <X size={12} />
                  </button>
                </span>
              )}

              {activeSlidePage && effectFramePreview?.presenterUrl && (
                // Solo visible al pasar el ratón por el escenario: fija, tapaba
                // contenido de la diapositiva que quedara debajo.
                <span className="stage-chip pointer-events-none absolute bottom-2 left-2 z-[5] opacity-0 transition-opacity duration-[var(--dur-hover)] ease-out group-hover/stage:opacity-100">
                  Arrastra al presentador para moverlo · esquinas para redimensionar
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="flex h-11 shrink-0 items-center gap-1.5 border-t border-border px-2.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={previousLabel}
              disabled={Boolean(effectFramePreview)}
              onClick={() => playback.jump(-1)}
            >
              <ChevronLeft size={17} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{previousLabel}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="primary"
              size="icon"
              className="h-8 w-8 rounded-full"
              onClick={() => void playback.togglePlayback()}
              disabled={!project.mediaUrl || Boolean(effectFramePreview)}
            >
              {playback.playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {playback.playing ? 'Pausar' : 'Reproducir'} <span className="ml-2 text-muted-foreground">Espacio</span>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={nextLabel}
              disabled={Boolean(effectFramePreview)}
              onClick={() => playback.jump(1)}
            >
              <ChevronRight size={17} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{nextLabel}</TooltipContent>
        </Tooltip>

        <div className="ml-1.5 flex shrink-0 items-baseline gap-1 font-mono tabular-nums">
          <strong className="text-[12px] tracking-tight text-foreground">
            {formatTime(isSource ? playback.sourceTimeS : playback.editTimeS ?? 0, true)}
          </strong>
          <span className="text-[10px] text-muted-foreground">
            / {formatTime(isSource ? project.timeline.durationS : project.preview.durationS, true)}
          </span>
        </div>

        <input
          className="scrub ml-1.5 flex-1"
          style={
            {
              '--scrub-progress': `${scrubMaxS > 0 ? Math.min(100, (scrubValueS / scrubMaxS) * 100) : 0}%`
            } as React.CSSProperties
          }
          type="range"
          aria-label="Posición de reproducción"
          title="Arrastra para buscar · ← → avanza 1 s · Inicio / Fin"
          min={0}
          max={scrubMaxS}
          step={0.01}
          value={scrubValueS}
          onChange={(event) => {
            const value = Number(event.target.value)
            if (isPreview) playback.seekEdit(value)
            else playback.seekFromTimeline(value)
          }}
          disabled={Boolean(effectFramePreview)}
        />
      </div>
    </section>
  )
}
