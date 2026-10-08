import { Check, Eye, MousePointerSquareDashed, RotateCcw, Scissors, Trash2 } from 'lucide-react'
import type {
  EditSegment,
  ProjectView,
  SlidePage,
  TimelineRegion,
  VisualEffectKind,
  VisualEffectRange
} from '../../../../shared/contracts'
import { formatTime } from '../../format'
import { SLIDE_STATUS_LABEL, slideConfidenceLabel, slideStatus } from '../../services/slide-status'
import { VISUAL_EFFECT_OPTIONS } from '../../services/visual-effects'
import { InspectorSection } from '../InspectorSection'
import { TakeInspectorTab } from '../TakeInspectorTab'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Field, RangeField } from '../ui/field'
import { ScrollArea } from '../ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

/**
 * Cuerpo contextual del Inspector: muestra las propiedades de **lo que está
 * seleccionado**, y nada más.
 *
 * Antes el Inspector tenía tres pestañas fijas (Efectos / Diapositivas /
 * Tomas) y había que acordarse de cuál correspondía a lo que se acababa de
 * pulsar en la línea de tiempo. La selección ya identifica el tipo de
 * elemento, así que la pestaña sobraba: aquí se resuelve por el propio estado
 * de selección, que es el mismo que resalta el bloque en la línea de tiempo y
 * el presentador en el visor.
 */
export type InspectorSelection =
  | { kind: 'slide'; page: SlidePage }
  | { kind: 'effect'; effect: VisualEffectRange }
  | { kind: 'region'; region: TimelineRegion | null }

interface SelectionInspectorProps {
  project: ProjectView
  selection: InspectorSelection
  busy: boolean
  /** Falso en previsualización: conservar/descartar/restaurar no aplican. */
  timelineEditable: boolean
  selectedSegment: EditSegment | null
  selectedSegmentId: string | null
  onSelectSegment: (segmentId: string) => void
  onSeekCandidate: (timeS: number) => void
  onSelectCandidate: (segmentId: string, candidateId: string) => void
  onRestoreCandidate: (segmentId: string) => void
  onUpdateSlidePage: (
    pageId: string,
    patch: Partial<Pick<SlidePage, 'startS' | 'endS' | 'enabled' | 'x' | 'y' | 'speakerWidth' | 'heightFraction'>>
  ) => void
  onUpdateEffect: (effectId: string, patch: Partial<Pick<VisualEffectRange, 'kind' | 'startS' | 'endS'>>) => void
  onDeleteEffect: (effectId: string) => void
  onPreviewEffects: () => void
  onKeepRegion: () => void
  onDiscardRegion: () => void
  onRestoreRegion: () => void
}

/** Campo numérico de segundos, con el mismo alto y tipografía en todo el panel. */
function SecondsInput({
  id,
  value,
  disabled,
  onCommit
}: {
  id: string
  value: number | null
  disabled: boolean
  onCommit: (value: number) => void
}): React.JSX.Element {
  return (
    <input
      // `key` con el valor: si el proyecto vuelve del backend con otro número
      // (recorte por solape, redondeo), el campo tiene que reflejarlo.
      key={`${id}-${value ?? 'empty'}`}
      id={id}
      type="number"
      min="0"
      step="0.1"
      defaultValue={value ?? ''}
      disabled={disabled}
      className="h-8 w-full rounded-md border border-border bg-background px-2 font-mono text-[11px] tabular-nums text-foreground outline-none transition-colors duration-[var(--dur-hover)] ease-out focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      onBlur={(event) => {
        const next = Number(event.currentTarget.value)
        if (Number.isFinite(next)) onCommit(next)
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.currentTarget.blur()
      }}
    />
  )
}

export function SlideProperties({
  page,
  chromaEnabled,
  busy,
  onUpdateSlidePage,
  onPreviewEffects
}: {
  page: SlidePage
  chromaEnabled: boolean
  busy: boolean
  onUpdateSlidePage: SelectionInspectorProps['onUpdateSlidePage']
  onPreviewEffects: () => void
}): React.JSX.Element {
  const status = slideStatus(page)
  const confidence = slideConfidenceLabel(page)
  return (
    <>
      <InspectorSection
        icon={Eye}
        title="Estado"
        description={page.recommendationReason}
        aside={<Badge variant="outline">{SLIDE_STATUS_LABEL[status]}</Badge>}
      >
        {confidence && <span className="text-[10px] text-muted-foreground">{confidence}</span>}
        <div className="grid grid-cols-2 gap-2">
          <Button
            size="sm"
            variant={page.enabled ? 'outline' : 'primary'}
            disabled={busy || (page.startS === null && page.recommendedStartS === null)}
            onClick={() => onUpdateSlidePage(page.id, { enabled: !page.enabled })}
          >
            {page.enabled ? 'Desactivar' : 'Activar'}
          </Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={onPreviewEffects}>
            <Eye size={13} /> Ver compuesto
          </Button>
        </div>
      </InspectorSection>

      <InspectorSection
        icon={Scissors}
        title="Tiempos"
        description="También se ajustan arrastrando el bloque en la pista DIAPOSITIVAS."
      >
        <div className="grid grid-cols-2 gap-2">
          <Field
            label="Inicio (s)"
            htmlFor={`slide-start-${page.id}`}
            readout={page.recommendedStartS === null ? undefined : `prop. ${page.recommendedStartS.toFixed(1)}`}
          >
            <SecondsInput
              id={`slide-start-${page.id}`}
              value={page.startS}
              disabled={busy}
              onCommit={(startS) => onUpdateSlidePage(page.id, { startS })}
            />
          </Field>
          <Field
            label="Fin (s)"
            htmlFor={`slide-end-${page.id}`}
            readout={page.recommendedEndS === null ? undefined : `prop. ${page.recommendedEndS.toFixed(1)}`}
          >
            <SecondsInput
              id={`slide-end-${page.id}`}
              value={page.endS}
              disabled={busy}
              onCommit={(endS) => onUpdateSlidePage(page.id, { endS })}
            />
          </Field>
        </div>
      </InspectorSection>

      <InspectorSection
        icon={MousePointerSquareDashed}
        title="Presentador"
        description={
          chromaEnabled
            ? 'Arrástralo sobre el visor, o ajústalo aquí. Las cifras son fracciones del cuadro.'
            : undefined
        }
      >
        {!chromaEnabled ? (
          <p className="m-0 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-2 text-[11px] leading-relaxed text-warning">
            Para recortar al presentador como silueta hace falta activar Chroma en la pestaña
            Proyecto. La diapositiva puede seguir en la línea de tiempo, pero el render fallará
            mientras esté activa sin Chroma.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            <RangeField label="Posición X" htmlFor={`slide-x-${page.id}`} value={page.x} min={-1} max={1} step={0.01} disabled={busy} readout={`${Math.round(page.x * 100)} %`} onValueChange={(x) => onUpdateSlidePage(page.id, { x })} />
            <RangeField label="Posición Y" htmlFor={`slide-y-${page.id}`} value={page.y} min={-1} max={1} step={0.01} disabled={busy} readout={`${Math.round(page.y * 100)} %`} onValueChange={(y) => onUpdateSlidePage(page.id, { y })} />
            <RangeField label="Ancho" htmlFor={`slide-width-${page.id}`} value={page.speakerWidth} min={0.02} max={1} step={0.01} disabled={busy} readout={`${Math.round(page.speakerWidth * 100)} %`} onValueChange={(speakerWidth) => onUpdateSlidePage(page.id, { speakerWidth })} />
            <RangeField label="Altura" htmlFor={`slide-height-${page.id}`} value={page.heightFraction} min={0.02} max={1} step={0.01} disabled={busy} readout={`${Math.round(page.heightFraction * 100)} %`} onValueChange={(heightFraction) => onUpdateSlidePage(page.id, { heightFraction })} />
          </div>
        )}
      </InspectorSection>
    </>
  )
}

export function EffectProperties({
  effect,
  busy,
  onUpdateEffect,
  onDeleteEffect
}: {
  effect: VisualEffectRange
  busy: boolean
  onUpdateEffect: SelectionInspectorProps['onUpdateEffect']
  onDeleteEffect: (effectId: string) => void
}): React.JSX.Element {
  return (
    <InspectorSection
      icon={Eye}
      title="Filtro"
      description="Arrastra el centro del bloque para moverlo y sus extremos para cambiar inicio y fin."
      aside={
        <Button variant="icon" size="icon" className="h-6 w-6" disabled={busy} aria-label="Eliminar efecto" title="Eliminar efecto" onClick={() => onDeleteEffect(effect.id)}>
          <Trash2 size={12} />
        </Button>
      }
    >
      <Field label="Filtro" htmlFor={`effect-kind-${effect.id}`}>
        <Select value={effect.kind} disabled={busy} onValueChange={(value) => onUpdateEffect(effect.id, { kind: value as VisualEffectKind })}>
          <SelectTrigger id={`effect-kind-${effect.id}`}><SelectValue /></SelectTrigger>
          <SelectContent>
            {VISUAL_EFFECT_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Inicio (s)" htmlFor={`effect-start-${effect.id}`} readout={formatTime(effect.startS)}>
          <SecondsInput
            id={`effect-start-${effect.id}`}
            value={effect.startS}
            disabled={busy}
            onCommit={(startS) => onUpdateEffect(effect.id, { startS: Math.min(startS, effect.endS - 0.1) })}
          />
        </Field>
        <Field label="Fin (s)" htmlFor={`effect-end-${effect.id}`} readout={formatTime(effect.endS)}>
          <SecondsInput
            id={`effect-end-${effect.id}`}
            value={effect.endS}
            disabled={busy}
            onCommit={(endS) => onUpdateEffect(effect.id, { endS: Math.max(endS, effect.startS + 0.1) })}
          />
        </Field>
      </div>
      <p className="m-0 text-[10px] tabular-nums text-muted-foreground">
        Duración {(effect.endS - effect.startS).toFixed(1)} s
      </p>
    </InspectorSection>
  )
}

export function SelectionInspector(props: SelectionInspectorProps): React.JSX.Element {
  const { project, selection, busy } = props

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4 px-3.5 pb-6 pt-3.5">
        {selection.kind === 'slide' && (
          <SlideProperties
            page={selection.page}
            chromaEnabled={project.renderSettings.chromaEnabled}
            busy={busy}
            onUpdateSlidePage={props.onUpdateSlidePage}
            onPreviewEffects={props.onPreviewEffects}
          />
        )}

        {selection.kind === 'effect' && (
          <EffectProperties
            effect={selection.effect}
            busy={busy}
            onUpdateEffect={props.onUpdateEffect}
            onDeleteEffect={props.onDeleteEffect}
          />
        )}

        {selection.kind === 'region' && (
          <>
            <InspectorSection
              icon={Scissors}
              title="Decisión de corte"
              description={
                selection.region
                  ? 'Decide si esta región entra en la edición final.'
                  : 'Selecciona una región en la pista CORTES para conservarla o descartarla.'
              }
              aside={
                selection.region ? (
                  <Badge variant={selection.region.keep ? 'brand' : 'default'}>
                    {selection.region.keep ? 'Conservado' : 'Descartado'}
                  </Badge>
                ) : undefined
              }
            >
              {selection.region ? (
                <>
                  <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-border bg-border">
                    <div className="bg-secondary px-2 py-1.5">
                      <dt className="text-[9px] uppercase tracking-wide text-muted-foreground">Inicio</dt>
                      <dd className="m-0 font-mono text-[10px] tabular-nums">{formatTime(selection.region.startS, true)}</dd>
                    </div>
                    <div className="bg-secondary px-2 py-1.5">
                      <dt className="text-[9px] uppercase tracking-wide text-muted-foreground">Fin</dt>
                      <dd className="m-0 font-mono text-[10px] tabular-nums">{formatTime(selection.region.endS, true)}</dd>
                    </div>
                    <div className="bg-secondary px-2 py-1.5">
                      <dt className="text-[9px] uppercase tracking-wide text-muted-foreground">Duración</dt>
                      <dd className="m-0 font-mono text-[10px] tabular-nums">
                        {formatTime(selection.region.endS - selection.region.startS, true)}
                      </dd>
                    </div>
                  </dl>
                  <div className="grid grid-cols-3 gap-2">
                    <Button size="sm" variant={selection.region.keep ? 'secondary' : 'primary'} disabled={busy || !props.timelineEditable} onClick={props.onKeepRegion}>
                      <Check size={13} /> Conservar
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy || !props.timelineEditable} onClick={props.onDiscardRegion}>
                      <Scissors size={13} /> Descartar
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy || !props.timelineEditable} onClick={props.onRestoreRegion}>
                      <RotateCcw size={13} /> Restaurar
                    </Button>
                  </div>
                  {!props.timelineEditable && (
                    <p className="m-0 text-[10px] leading-relaxed text-muted-foreground">
                      Vuelve a «Original» o «Propuesta» para cambiar esta decisión: la
                      previsualización muestra el resultado, no se edita.
                    </p>
                  )}
                </>
              ) : (
                <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] leading-relaxed text-muted-foreground">
                  Nada seleccionado. Pulsa una región, un filtro o una diapositiva en la línea de
                  tiempo y sus propiedades aparecerán aquí.
                </div>
              )}
            </InspectorSection>

            <div className="border-t border-border pt-3">
              <TakeInspectorTab
                project={project}
                selectedSegment={props.selectedSegment}
                selectedSegmentId={props.selectedSegmentId}
                busy={busy}
                onSelectSegment={props.onSelectSegment}
                onSeekCandidate={props.onSeekCandidate}
                onSelectCandidate={props.onSelectCandidate}
                onRestoreCandidate={props.onRestoreCandidate}
              />
            </div>
          </>
        )}
      </div>
    </ScrollArea>
  )
}
