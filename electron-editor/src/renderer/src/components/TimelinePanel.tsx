import { useMemo, useState } from 'react'
import {
  Check,
  Crosshair,
  Redo2,
  RotateCcw,
  Scissors,
  Split,
  Undo2,
  ZoomIn,
  ZoomOut
} from 'lucide-react'
import type { ProjectView, SlidePage, TimelineMedia, TimelineRegion, VisualEffectRange } from '../../../shared/contracts'
import type { PreviewMode, ThemeMode } from '../types/editor'
import { TIMELINE_PALETTES, TIMELINE_SCROLLBAR_HEIGHT, Timeline, timelineHeight, timelineTracks } from '../Timeline'
import { editedMedia, editedRegions } from '../services/preview-timeline'
import { formatTime } from '../format'
import { Button } from './ui/button'
import { Separator } from './ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { TIMELINE_GUTTER_WIDTH, TimelineTrackGutter } from './TimelineTrackGutter'
import { cn } from '../lib/utils'

interface TimelinePanelProps {
  className?: string
  style?: React.CSSProperties
  project: ProjectView
  media: TimelineMedia | null
  mediaLoading: boolean
  busy: boolean
  sourceTimeS: number
  editTimeS: number | null
  previewMode: PreviewMode
  pixelsPerSecond: number
  selectedRegionId: string | null
  selectedRegion: TimelineRegion | null
  theme: ThemeMode
  onPixelsPerSecondChange: (value: number) => void
  onSelectRegion: (regionId: string) => void
  onSeek: (timeS: number) => void
  onSeekEdit: (editTimeS: number) => void
  onMoveBoundary: (oldTimeS: number, newTimeS: number) => void
  onKeepRegion: () => void
  onDiscardRegion: () => void
  onRestoreRegion: () => void
  onSplit: () => void
  onUndo: () => void
  onRedo: () => void
  selectedEffectId: string | null
  onSelectEffect: (effectId: string) => void
  onUpdateEffectRange: (effectId: string, patch: Pick<VisualEffectRange, 'startS' | 'endS'>) => void
  slidePages: SlidePage[]
  selectedSlideId: string | null
  onSelectSlide: (slideId: string) => void
  onUpdateSlideTiming: (slideId: string, patch: Pick<SlidePage, 'startS' | 'endS'>) => void
}

/**
 * Acción de la barra de la línea de tiempo.
 *
 * La etiqueta solo aparece cuando hay sitio (`hidden xl:inline`). Con el
 * texto siempre visible, en una ventana del ancho mínimo de la aplicación
 * (1120px) el grupo de la derecha —zoom, deshacer, estado de los medios—
 * quedaba empujado fuera del panel. El tooltip cubre el caso estrecho.
 */
function TimelineAction({
  icon: Icon,
  label,
  shortcut,
  disabled,
  onClick
}: {
  icon: typeof Check
  label: string
  shortcut?: string
  disabled?: boolean
  onClick: () => void
}): React.JSX.Element {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label={label}
          className="h-7 shrink-0 gap-1.5 px-1.5 text-[11px] xl:px-2"
          disabled={disabled}
          onClick={onClick}
        >
          <Icon size={13} /> <span className="hidden xl:inline">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {label}
        {shortcut && <span className="ml-2 text-muted-foreground">{shortcut}</span>}
      </TooltipContent>
    </Tooltip>
  )
}

export function TimelinePanel({
  className,
  style,
  project,
  media,
  mediaLoading,
  busy,
  sourceTimeS,
  editTimeS,
  previewMode,
  pixelsPerSecond,
  selectedRegionId,
  selectedRegion,
  theme,
  onPixelsPerSecondChange,
  onSelectRegion,
  onSeek,
  onSeekEdit,
  onMoveBoundary,
  onKeepRegion,
  onDiscardRegion,
  onRestoreRegion,
  onSplit,
  onUndo,
  onRedo,
  selectedEffectId,
  onSelectEffect,
  onUpdateEffectRange,
  slidePages,
  selectedSlideId,
  onSelectSlide,
  onUpdateSlideTiming
}: TimelinePanelProps): React.JSX.Element {
  const palette = TIMELINE_PALETTES[theme]
  const [followPlayhead, setFollowPlayhead] = useState(false)
  // En modo previsualizacion la linea de tiempo deja de ser la del video
  // fuente y pasa a ser la de la edicion final, derivada de project.preview.
  const isPreview = previewMode === 'preview'
  const previewRegions = useMemo(() => editedRegions(project), [project])
  const previewMedia = useMemo(() => editedMedia(project, media), [project, media])
  const hasPreviewClips = previewRegions.length > 0
  const visibleSlides = isPreview ? [] : slidePages
  const tracks = useMemo(() => timelineTracks(visibleSlides.length > 0), [visibleSlides.length])
  const height = timelineHeight(tracks)

  return (
    <section style={style} className={cn('flex min-w-0 shrink-0 flex-col overflow-hidden bg-card', className)}>
      <header className="flex h-9 shrink-0 items-center gap-1.5 border-b border-border px-2.5">
        <span className="panel-eyebrow shrink-0">
          {isPreview ? 'Edición final' : 'Línea de tiempo'}
        </span>

        {/* Lectura de la selección: sin ella, los botones de la derecha se
            activaban y desactivaban sin decir sobre qué actúan. */}
        <span
          className={cn(
            'min-w-0 truncate text-[11px] tabular-nums text-muted-foreground',
            // En previsualización no hay acciones de edición compitiendo por
            // el sitio, así que la lectura cabe siempre.
            !isPreview && 'hidden 2xl:block'
          )}
        >
          {isPreview
            ? `${previewRegions.length} cortes unidos · ${formatTime(project.preview.durationS)}`
            : selectedRegion
              ? `${formatTime(selectedRegion.startS, true)} – ${formatTime(selectedRegion.endS, true)} · ${selectedRegion.keep ? 'Conservado' : 'Descartado'}`
              : `${project.timeline.regions.length} regiones · ${project.timeline.cutPointsS.length} cortes`}
        </span>

        {!isPreview && (
          <>
            <Separator orientation="vertical" className="mx-1 h-4" />
            <TimelineAction icon={Check} label="Conservar" disabled={!selectedRegion || busy} onClick={onKeepRegion} />
            <TimelineAction icon={Scissors} label="Descartar" disabled={!selectedRegion || busy} onClick={onDiscardRegion} />
            <TimelineAction icon={RotateCcw} label="Restaurar" disabled={!selectedRegion || busy} onClick={onRestoreRegion} />
            <TimelineAction icon={Split} label="Dividir" shortcut="en el cabezal" disabled={busy} onClick={onSplit} />
          </>
        )}

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <span
            title={media?.warning ?? 'Fotogramas pequeños del video y forma de onda del audio'}
            className="mr-1 hidden items-center gap-1.5 text-[10px] text-muted-foreground xl:inline-flex"
          >
            {mediaLoading && <span className="live-dot" />}
            {mediaLoading ? 'Generando medios…' : media?.warning ? 'Medios parciales' : 'Medios listos'}
          </span>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="icon"
                size="icon"
                aria-pressed={followPlayhead}
                data-active={followPlayhead ? 'true' : 'false'}
                className="h-7 w-7 data-[active=true]:border-primary/50 data-[active=true]:text-primary"
                onClick={() => setFollowPlayhead((value) => !value)}
              >
                <Crosshair size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Seguir el cabezal al reproducir</TooltipContent>
          </Tooltip>

          <Separator orientation="vertical" className="mx-0.5 h-4" />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="icon"
                size="icon"
                className="h-7 w-7"
                aria-label="Alejar"
                disabled={pixelsPerSecond <= 10}
                onClick={() => onPixelsPerSecondChange(Math.max(10, pixelsPerSecond / 1.35))}
              >
                <ZoomOut size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Alejar</TooltipContent>
          </Tooltip>
          <span className="w-11 text-center text-[10px] tabular-nums text-muted-foreground">
            {Math.round(pixelsPerSecond)} px/s
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="icon"
                size="icon"
                className="h-7 w-7"
                aria-label="Acercar"
                disabled={pixelsPerSecond >= 220}
                onClick={() => onPixelsPerSecondChange(Math.min(220, pixelsPerSecond * 1.35))}
              >
                <ZoomIn size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Acercar</TooltipContent>
          </Tooltip>

          <Separator orientation="vertical" className="mx-0.5 h-4" />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="icon" size="icon" className="h-7 w-7" aria-label="Deshacer" disabled={!project.canUndo || busy} onClick={onUndo}>
                <Undo2 size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Deshacer <span className="ml-2 text-muted-foreground">Ctrl+Z</span></TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="icon" size="icon" className="h-7 w-7" aria-label="Rehacer" disabled={!project.canRedo || busy} onClick={onRedo}>
                <Redo2 size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Rehacer <span className="ml-2 text-muted-foreground">Ctrl+Shift+Z</span></TooltipContent>
          </Tooltip>
        </div>
      </header>

      {isPreview && !hasPreviewClips ? (
        <div className="grid flex-1 place-items-center px-6 text-center">
          <div className="max-w-[320px]">
            <Scissors size={22} className="mx-auto mb-2 text-muted-foreground/60" />
            <strong className="block text-xs">Sin cortes aceptados</strong>
            <span className="mt-1 block text-[11px] leading-relaxed text-muted-foreground">
              Marca al menos una región como conservada para ver aquí la edición final.
            </span>
          </div>
        </div>
      ) : (
        <div className="timeline-body relative flex min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
          <TimelineTrackGutter
            tracks={tracks}
            height={height + TIMELINE_SCROLLBAR_HEIGHT}
            colors={{
              video: palette.rulerText,
              audio: palette.waveformLine,
              effects: palette.effectFill,
              regions: palette.keepFill,
              slides: palette.slideFill
            }}
          />
          <div className="min-w-0 flex-1">
            <Timeline
              durationS={isPreview ? project.preview.durationS : project.timeline.durationS}
              regions={isPreview ? previewRegions : project.timeline.regions}
              playheadS={isPreview ? editTimeS ?? 0 : sourceTimeS}
              followPlayhead={followPlayhead}
              selectedRegionId={isPreview ? null : selectedRegionId}
              media={isPreview ? previewMedia : media}
              pixelsPerSecond={pixelsPerSecond}
              theme={theme}
              readOnly={isPreview || busy}
              label={isPreview ? 'Línea de tiempo de la edición final' : 'Línea de tiempo del video fuente'}
              onSeek={isPreview ? onSeekEdit : onSeek}
              onSelectRegion={onSelectRegion}
              onMoveBoundary={onMoveBoundary}
              effectRanges={isPreview ? [] : project.effectRanges}
              selectedEffectId={isPreview ? null : selectedEffectId}
              onSelectEffect={onSelectEffect}
              onUpdateEffectRange={(effectId, startS, endS) => onUpdateEffectRange(effectId, { startS, endS })}
              slidePages={visibleSlides}
              selectedSlideId={isPreview ? null : selectedSlideId}
              onSelectSlide={onSelectSlide}
              onUpdateSlideTiming={(slideId, startS, endS) => onUpdateSlideTiming(slideId, { startS, endS })}
            />
          </div>

          {/* Mientras el backend genera miniaturas y forma de onda, la línea de
              tiempo está dibujada pero vacía. El esqueleto dice que falta
              contenido por llegar sin bloquear nada: las regiones y el cabezal
              se siguen viendo y se pueden seguir usando. */}
          {mediaLoading && (
            <div
              aria-hidden
              className="pointer-events-none absolute inset-y-0 right-0 flex flex-col gap-1 p-1 pt-[27px]"
            style={{ left: TIMELINE_GUTTER_WIDTH }}
            >
              <div className="skeleton h-[54px] w-full" />
              <div className="skeleton h-[36px] w-full" />
            </div>
          )}
        </div>
      )}
    </section>
  )
}
