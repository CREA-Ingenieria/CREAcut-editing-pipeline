import { Check, Clapperboard } from 'lucide-react'
import type { EditSegment, ProjectView } from '../../../shared/contracts'
import { formatTime } from '../format'
import { cn } from '../lib/utils'
import { InspectorSection } from './InspectorSection'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'

/**
 * Tomas alternativas de la oración seleccionada.
 *
 * Ya no trae su propio `ScrollArea`: vive dentro del cuerpo contextual del
 * Inspector, que es quien desplaza. Dos áreas de desplazamiento anidadas
 * dejaban la lista de tomas con su propia barra dentro del panel.
 */
interface TakeInspectorTabProps {
  project: ProjectView
  selectedSegment: EditSegment | null
  selectedSegmentId: string | null
  busy: boolean
  onSelectSegment: (segmentId: string) => void
  onSeekCandidate: (timeS: number) => void
  onSelectCandidate: (segmentId: string, candidateId: string) => void
  onRestoreCandidate: (segmentId: string) => void
}

export function TakeInspectorTab(props: TakeInspectorTabProps): React.JSX.Element {
  const { project, selectedSegment, selectedSegmentId, busy } = props
  const segments = project.project.segments

  return (
    <InspectorSection
      icon={Clapperboard}
      title="Tomas de la oración"
      description={
        segments.length === 0
          ? undefined
          : 'La automatización propone una toma; la decisión final es tuya.'
      }
      aside={
        selectedSegment ? (
          <button
            type="button"
            className="text-[10px] font-semibold text-primary outline-none transition-opacity duration-[var(--dur-hover)] hover:underline disabled:opacity-40"
            disabled={busy}
            onClick={() => props.onRestoreCandidate(selectedSegment.id)}
          >
            Restaurar automática
          </button>
        ) : undefined
      }
    >
      {segments.length === 0 ? (
        <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] leading-relaxed text-muted-foreground">
          Este proyecto no tiene oraciones del guion asociadas.
        </div>
      ) : (
        <>
          <Select value={selectedSegmentId ?? ''} onValueChange={props.onSelectSegment}>
            <SelectTrigger id="segment-select" aria-label="Oración">
              <SelectValue placeholder="Selecciona una oración" />
            </SelectTrigger>
            <SelectContent>
              {segments.map((segment, index) => (
                <SelectItem key={segment.id} value={segment.id}>
                  {index + 1}. {segment.script_text}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {selectedSegment ? (
            <>
              <blockquote className="m-0 rounded-r-md border-l-2 border-primary bg-background px-3 py-2 text-[11px] leading-relaxed text-foreground/85">
                “{selectedSegment.script_text}”
              </blockquote>

              <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border">
                <div className="min-w-0 bg-secondary px-2 py-1.5">
                  <dt className="text-[9px] uppercase tracking-wide text-muted-foreground">Rango fuente</dt>
                  <dd className="m-0 truncate font-mono text-[10px] tabular-nums">
                    {selectedSegment.source_start_s === null
                      ? 'Sin toma'
                      : `${formatTime(selectedSegment.source_start_s, true)} – ${formatTime(selectedSegment.source_end_s ?? 0, true)}`}
                  </dd>
                </div>
                <div className="min-w-0 bg-secondary px-2 py-1.5">
                  <dt className="text-[9px] uppercase tracking-wide text-muted-foreground">Selección</dt>
                  <dd className="m-0 truncate text-[10px]">
                    {selectedSegment.selected_candidate_id === selectedSegment.automatic_selection.recommended_candidate_id
                      ? 'Recomendada'
                      : 'Modificada'}
                    {' · '}
                    {selectedSegment.automatic_selection.selection_reason.replaceAll('_', ' ')}
                  </dd>
                </div>
              </dl>

              {selectedSegment.candidates.length === 0 ? (
                <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] leading-relaxed text-muted-foreground">
                  No se detectaron tomas alternativas para esta oración.
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {selectedSegment.candidates.map((candidate, index) => {
                    const selected = candidate.id === selectedSegment.selected_candidate_id
                    const recommended = candidate.id === selectedSegment.automatic_selection.recommended_candidate_id
                    return (
                      <div
                        key={candidate.id}
                        className={cn(
                          'rounded-md border border-border bg-secondary p-2.5 transition-colors duration-[var(--dur-hover)] ease-out hover:border-muted-foreground/40',
                          selected && 'border-brand-strong/45 bg-brand-soft'
                        )}
                      >
                        <button
                          className="w-full cursor-pointer border-0 bg-transparent p-0 text-left text-inherit outline-none"
                          title="Llevar el cabezal al inicio de esta toma"
                          onClick={() => props.onSeekCandidate(candidate.source_start_s)}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <strong className="text-[11px]">Toma {index + 1}</strong>
                            <span className="text-[11px] font-bold tabular-nums text-primary">
                              {Math.round(candidate.score * 100)}%
                            </span>
                          </div>
                          <p className="my-1.5 text-[10px] leading-relaxed text-foreground/70">
                            {candidate.transcript_text || 'Sin transcripción'}
                          </p>
                          <div className="flex flex-wrap items-center gap-1.5 text-[9px] tabular-nums text-muted-foreground/80">
                            <span>
                              {formatTime(candidate.source_start_s, true)} – {formatTime(candidate.source_end_s, true)}
                            </span>
                            {recommended && <Badge variant="default">Recomendada</Badge>}
                            {selected && (
                              <Badge variant="brand" className="gap-1">
                                <Check size={10} /> En uso
                              </Badge>
                            )}
                          </div>
                        </button>
                        {!selected && (
                          <Button
                            variant="secondary"
                            size="sm"
                            className="mt-2 h-7 w-full border-brand-strong/25 bg-brand-soft text-[10px] text-primary hover:bg-brand-soft/80"
                            disabled={busy}
                            onClick={() => props.onSelectCandidate(selectedSegment.id, candidate.id)}
                          >
                            Usar esta toma
                          </Button>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          ) : (
            <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] leading-relaxed text-muted-foreground">
              Elige una oración arriba, o pulsa una frase del guion en el panel izquierdo.
            </div>
          )}
        </>
      )}
    </InspectorSection>
  )
}
