import { FolderOpen, Presentation, Sparkles, Trash2 } from 'lucide-react'
import type { SlideDeck, SlidePage } from '../../../shared/contracts'
import { compactPath } from '../format'
import { SLIDE_STATUS_LABEL, slideConfidenceLabel, slideStatus } from '../services/slide-status'
import { Badge, type BadgeProps } from './ui/badge'
import { Button } from './ui/button'
import { ScrollArea } from './ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { cn } from '../lib/utils'

/**
 * Biblioteca de diapositivas: el material importado del proyecto.
 *
 * Vive en el panel izquierdo, junto a la transcripción y el guion, porque es
 * lo mismo que ellas: material de partida que se arrastra al montaje. Antes
 * estaba dentro del Inspector, mezclada con los ajustes de la diapositiva
 * **seleccionada** — es decir, el catálogo y las propiedades de un elemento
 * compartían panel, y elegir una diapositiva reordenaba el sitio donde
 * estabas mirando.
 *
 * Aquí solo se importa, se analiza y se elige. Todo lo que se ajusta de una
 * diapositiva concreta (tiempos, posición del presentador) pasó al Inspector,
 * que es contextual.
 */
interface SlidesLibraryProps {
  slides: SlideDeck | null
  busy: boolean
  selectedSlideId: string | null
  onSelectSlide: (slideId: string) => void
  onPickSlides: () => void
  onPickSlidesFolder: () => void
  onRemoveSlides: () => void
  onRecommendSlides: () => void
  onAcceptSlideRecommendations: () => void
  onUpdateSlidePage: (pageId: string, patch: Partial<Pick<SlidePage, 'enabled'>>) => void
  onAddSlideToTimeline: (pageId: string) => void
}

const STATUS_BADGE_VARIANT: Record<ReturnType<typeof slideStatus>, BadgeProps['variant']> = {
  unanalyzed: 'default',
  proposed: 'outline',
  active: 'brand',
  modified: 'warning',
  disabled: 'default'
}

export function SlidesLibrary({
  slides,
  busy,
  selectedSlideId,
  onSelectSlide,
  onPickSlides,
  onPickSlidesFolder,
  onRemoveSlides,
  onRecommendSlides,
  onAcceptSlideRecommendations,
  onUpdateSlidePage,
  onAddSlideToTimeline
}: SlidesLibraryProps): React.JSX.Element {
  if (!slides) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-5 text-center">
        <span className="grid h-11 w-11 place-items-center rounded-full border border-dashed border-border text-muted-foreground">
          <Presentation size={19} />
        </span>
        <div>
          <strong className="block text-xs">Sin diapositivas</strong>
          <p className="mx-auto mt-1 max-w-[240px] text-[11px] leading-relaxed text-muted-foreground">
            Importa un PowerPoint, un PDF o una carpeta de imágenes. Cada diapositiva se convierte a
            PNG antes de usarse; el archivo original nunca se modifica.
          </p>
        </div>
        <div className="flex w-full max-w-[260px] gap-2">
          <Button size="sm" className="flex-1" disabled={busy} onClick={onPickSlides}>
            <Presentation size={13} /> PPTX o PDF
          </Button>
          <Button variant="outline" size="sm" className="flex-1" disabled={busy} onClick={onPickSlidesFolder}>
            <FolderOpen size={13} /> Carpeta
          </Button>
        </div>
      </div>
    )
  }

  const hasRecommendations = slides.pages.some((page) => page.recommendedStartS !== null)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1.5 border-b border-border px-2.5 py-2">
        <div className="min-w-0 flex-1">
          <strong className="block truncate text-[11px] font-semibold" title={slides.sourcePath}>
            {compactPath(slides.sourcePath)}
          </strong>
          <span className="block text-[10px] text-muted-foreground">
            {slides.pages.length} diapositivas · {slides.renderer}
          </span>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="icon" size="icon" className="h-7 w-7" aria-label="Reemplazar archivo" disabled={busy} onClick={onPickSlides}>
              <Presentation size={13} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Reemplazar por otro PPTX o PDF</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="icon" size="icon" className="h-7 w-7" aria-label="Reemplazar por carpeta" disabled={busy} onClick={onPickSlidesFolder}>
              <FolderOpen size={13} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Reemplazar por una carpeta de imágenes</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="icon" size="icon" className="h-7 w-7" aria-label="Quitar diapositivas" disabled={busy} onClick={onRemoveSlides}>
              <Trash2 size={13} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Quitar las diapositivas del proyecto</TooltipContent>
        </Tooltip>
      </div>

      <div className="flex shrink-0 items-center gap-2 border-b border-border px-2.5 py-2">
        <Button variant="outline" size="sm" className="h-7 flex-1 text-[11px]" disabled={busy} onClick={onRecommendSlides}>
          <Sparkles size={13} /> Analizar
        </Button>
        <Button
          variant="primary"
          size="sm"
          className="h-7 flex-1 text-[11px]"
          disabled={busy || !hasRecommendations}
          title={hasRecommendations ? undefined : 'Ejecuta primero «Analizar» para tener propuestas que aceptar'}
          onClick={onAcceptSlideRecommendations}
        >
          Aceptar todas
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="grid grid-cols-2 gap-1.5 p-2">
          {slides.pages.map((page) => {
            const status = slideStatus(page)
            const confidence = slideConfidenceLabel(page)
            const selected = page.id === selectedSlideId
            return (
              // No es un <button> nativo: contiene botones propios
              // (Aceptar/Activar/Desactivar) y un <button> no puede anidar otro.
              <div
                key={page.id}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                title={page.text ? page.text.slice(0, 160) : `Diapositiva ${page.index + 1}`}
                className={cn(
                  'slide-tile group overflow-hidden rounded-md border bg-background text-left',
                  selected ? 'border-primary' : 'border-border'
                )}
                onClick={() => onSelectSlide(page.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelectSlide(page.id)
                  }
                }}
              >
                <div className="relative">
                  {page.thumbnailUrl ? (
                    <img
                      src={page.thumbnailUrl}
                      alt={`Diapositiva ${page.index + 1}`}
                      loading="lazy"
                      className="block aspect-video w-full bg-secondary object-contain"
                    />
                  ) : (
                    <div className="grid aspect-video place-items-center bg-secondary text-[10px] text-muted-foreground">
                      Sin miniatura
                    </div>
                  )}
                  <span className="absolute left-1 top-1 rounded bg-black/70 px-1 text-[9px] font-bold tabular-nums text-white">
                    {page.index + 1}
                  </span>
                </div>
                <div className="flex flex-col gap-1 p-1.5">
                  <Badge variant={STATUS_BADGE_VARIANT[status]} className="w-fit px-1.5 py-0.5 text-[8px]">
                    {SLIDE_STATUS_LABEL[status]}
                  </Badge>
                  {confidence && <span className="truncate text-[9px] text-muted-foreground">{confidence}</span>}
                  <div className="flex flex-wrap gap-1">
                    {status === 'proposed' && (
                      <Button size="sm" className="h-5 px-1.5 text-[9px]" disabled={busy} onClick={(event) => { event.stopPropagation(); onUpdateSlidePage(page.id, { enabled: true }) }}>
                        Aceptar
                      </Button>
                    )}
                    {status === 'unanalyzed' && (
                      <Button variant="outline" size="sm" className="h-5 px-1.5 text-[9px]" disabled={busy} onClick={(event) => { event.stopPropagation(); onAddSlideToTimeline(page.id) }}>
                        Agregar
                      </Button>
                    )}
                    {(status === 'active' || status === 'modified') && (
                      <Button variant="outline" size="sm" className="h-5 px-1.5 text-[9px]" disabled={busy} onClick={(event) => { event.stopPropagation(); onUpdateSlidePage(page.id, { enabled: false }) }}>
                        Desactivar
                      </Button>
                    )}
                    {status === 'disabled' && (
                      <Button variant="outline" size="sm" className="h-5 px-1.5 text-[9px]" disabled={busy} onClick={(event) => { event.stopPropagation(); onUpdateSlidePage(page.id, { enabled: true }) }}>
                        Activar
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </ScrollArea>
    </div>
  )
}
