import {
  AudioLines,
  Captions,
  Eye,
  Image,
  Layers3,
  ListTree,
  Paintbrush,
  Plus,
  Sparkles,
  WandSparkles
} from 'lucide-react'
import { useState } from 'react'
import type {
  ProjectRenderSettings,
  ProjectRenderSettingsPatch,
  VisualEffectKind,
  VisualEffectRange
} from '../../../../shared/contracts'
import { compactPath, formatTime } from '../../format'
import { VISUAL_EFFECT_OPTIONS, visualEffectLabel } from '../../services/visual-effects'
import { InspectorSection } from '../InspectorSection'
import { SettingToggle } from '../SettingToggle'
import { Button } from '../ui/button'
import { Field, RangeField } from '../ui/field'
import { ScrollArea } from '../ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { cn } from '../../lib/utils'

/**
 * Ajustes que valen para el proyecto entero: chroma, fondo, gráficos, audio,
 * transiciones y el catálogo de filtros con duración.
 *
 * Incluye los controles del filtro activo y la revisión de tomas.
 */
interface ProjectInspectorProps {
  effectEditor?: React.ReactNode
  children?: React.ReactNode
  settings: ProjectRenderSettings
  busy: boolean
  onUpdate: (patch: ProjectRenderSettingsPatch) => void
  onPickBackground: () => void
  onPreviewEffects: () => void
  effectRanges: VisualEffectRange[]
  selectedEffectId: string | null
  sourceTimeS: number
  onAddEffect: (kind: VisualEffectKind) => void
  onSelectEffect: (effectId: string) => void
}

const TRANSITION_OPTIONS: Array<{ value: ProjectRenderSettings['transitionType']; label: string }> = [
  { value: 'cut', label: 'Corte directo' },
  { value: 'dissolve', label: 'Disolvencia' },
  { value: 'fade_black', label: 'Fundido a negro' },
  { value: 'wipe_left', label: 'Barrido lateral' },
  { value: 'slide_left', label: 'Deslizamiento lateral' }
]

/**
 * Tope de la duración de la transición.
 *
 * No es una decisión de interfaz: `bridge.py` rechaza con un error cualquier
 * `crossfadeS` fuera de 0–0.5 s. El deslizador tiene que terminar exactamente
 * donde termina lo que el backend acepta, o el usuario puede elegir un valor
 * que la aplicación no va a poder guardar.
 */
const CROSSFADE_MAX_S = 0.5

/**
 * Cómo se lee la duración elegida.
 *
 * Una cifra sola («0.35 s») no dice si es mucho o poco, así que se acompaña del
 * carácter que tendrá el corte. Los umbrales son los de montaje habitual: por
 * debajo de 0.12 s la transición se percibe casi como un corte seco, y cerca
 * del tope se vuelve un recurso narrativo, no un empalme.
 */
function crossfadeCharacter(seconds: number): string {
  if (seconds <= 0) return 'Sin transición'
  if (seconds < 0.12) return 'Casi un corte'
  if (seconds < 0.22) return 'Ágil'
  if (seconds < 0.36) return 'Equilibrada'
  return 'Pausada'
}

export function ProjectInspector({
  effectEditor,
  children,
  settings,
  busy,
  onUpdate,
  onPickBackground,
  onPreviewEffects,
  effectRanges,
  selectedEffectId,
  sourceTimeS,
  onAddEffect,
  onSelectEffect
}: ProjectInspectorProps): React.JSX.Element {
  const [newEffectKind, setNewEffectKind] = useState<VisualEffectKind>('cinematic')
  const transitionsOff = settings.transitionType === 'cut'

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4 px-3.5 pb-6 pt-3.5">
        <InspectorSection
          icon={Eye}
          title="Comprobar el render"
          description="Los filtros y las transiciones se ven al reproducir. El fotograma exacto permite comprobar además chroma, fondo y piel."
        >
          <Button variant="secondary" size="sm" className="w-full" disabled={busy} onClick={onPreviewEffects}>
            <Eye size={14} /> Previsualizar fotograma en {formatTime(sourceTimeS, true)}
          </Button>
        </InspectorSection>

        <InspectorSection
          icon={Sparkles}
          title="Filtros con duración"
          description="Se agregan en el cabezal y aparecen como bloques arrastrables en la pista EFECTOS."
        >
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Select value={newEffectKind} disabled={busy} onValueChange={(value) => setNewEffectKind(value as VisualEffectKind)}>
              <SelectTrigger aria-label="Filtro visual"><SelectValue /></SelectTrigger>
              <SelectContent>
                {VISUAL_EFFECT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="primary" size="sm" className="h-9" disabled={busy} onClick={() => onAddEffect(newEffectKind)}>
              <Plus size={14} /> Agregar
            </Button>
          </div>

          {effectRanges.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] leading-relaxed text-muted-foreground">
              Todavía no hay filtros temporales. El que agregues empezará en el cabezal y durará 5 s.
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {effectRanges.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={cn(
                    'flex items-baseline justify-between gap-2 rounded-md border px-2.5 py-1.5 text-left',
                    'transition-colors duration-[var(--dur-hover)] ease-out',
                    item.id === selectedEffectId
                      ? 'border-primary bg-brand-soft'
                      : 'border-border bg-secondary hover:border-primary/50'
                  )}
                  onClick={() => onSelectEffect(item.id)}
                >
                  <strong className="truncate text-[11px] font-semibold">{visualEffectLabel(item.kind)}</strong>
                  <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                    {formatTime(item.startS)} – {formatTime(item.endS)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </InspectorSection>

        {effectEditor}

        <InspectorSection
          icon={WandSparkles}
          title="Transición entre cortes"
          description="Se aplica a todos los cortes. Reproduce en modo Previsualización para verla."
        >
          <Field label="Estilo" htmlFor="transition-type-select">
            <Select value={settings.transitionType} disabled={busy} onValueChange={(value) => onUpdate({ transitionType: value as ProjectRenderSettings['transitionType'] })}>
              <SelectTrigger id="transition-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {TRANSITION_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <RangeField
            label="Duración"
            htmlFor="crossfade-range"
            value={settings.crossfadeS}
            min={0}
            max={CROSSFADE_MAX_S}
            step={0.05}
            disabled={busy || transitionsOff}
            readout={`${settings.crossfadeS.toFixed(2)} s · ${crossfadeCharacter(settings.crossfadeS)}`}
            minLabel="0 s"
            maxLabel={`${CROSSFADE_MAX_S.toFixed(2)} s`}
            hint={transitionsOff ? 'El corte directo no tiene duración que ajustar.' : undefined}
            onValueChange={(crossfadeS) => onUpdate({ crossfadeS })}
          />
        </InspectorSection>

        <InspectorSection icon={Paintbrush} title="Imagen y color">
          <SettingToggle
            icon={Layers3}
            title="Reemplazo de chroma"
            description="Elimina el fondo verde durante la exportación. Necesario para superponer al presentador sobre diapositivas."
            checked={settings.chromaEnabled}
            disabled={busy}
            onCheckedChange={(chromaEnabled) => onUpdate({ chromaEnabled })}
          />

          <Field label="Fondo del chroma" readout={settings.backgroundImage ? undefined : 'Blanco'}>
            <div className="flex items-center gap-2 rounded-md border border-border bg-secondary p-2">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-background text-primary">
                <Image size={15} />
              </span>
              <span
                className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground"
                title={settings.backgroundImage ?? undefined}
              >
                {settings.backgroundImage ? compactPath(settings.backgroundImage) : 'Blanco automático'}
              </span>
              <Button variant="secondary" size="sm" className="h-7 shrink-0 text-[10px]" disabled={busy} onClick={onPickBackground}>
                Elegir
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 shrink-0 text-[10px]"
                disabled={busy || !settings.backgroundImage}
                onClick={() => onUpdate({ backgroundImage: null })}
              >
                Quitar
              </Button>
            </div>
          </Field>

          <SettingToggle
            icon={Sparkles}
            title="Corrección de piel"
            description="Ajusta únicamente los tonos de piel detectados."
            checked={settings.skinCorrectionEnabled}
            disabled={busy}
            onCheckedChange={(skinCorrectionEnabled) => onUpdate({ skinCorrectionEnabled })}
          />
          <RangeField
            label="Intensidad de corrección"
            htmlFor="skin-strength-range"
            value={settings.skinCorrectionStrength}
            min={0.2}
            max={1}
            step={0.05}
            disabled={busy || !settings.skinCorrectionEnabled}
            readout={`${Math.round(settings.skinCorrectionStrength * 100)} %`}
            minLabel="Sutil"
            maxLabel="Completa"
            onValueChange={(skinCorrectionStrength) => onUpdate({ skinCorrectionStrength })}
          />
        </InspectorSection>

        <InspectorSection icon={Captions} title="Elementos gráficos">
          <SettingToggle icon={ListTree} title="Listas explicativas" description="Detecta enumeraciones del guion y genera paneles." checked={settings.listOverlaysEnabled} disabled={busy} onCheckedChange={(listOverlaysEnabled) => onUpdate({ listOverlaysEnabled })} />
          <SettingToggle icon={Captions} title="Términos clave" description="Muestra tarjetas para el vocabulario configurado." checked={settings.termOverlaysEnabled} disabled={busy} onCheckedChange={(termOverlaysEnabled) => onUpdate({ termOverlaysEnabled })} />
          <SettingToggle icon={Sparkles} title="Destacados del guion" description="Convierte el texto en negrita del Markdown en tarjetas." checked={settings.boldCardsEnabled} disabled={busy} onCheckedChange={(boldCardsEnabled) => onUpdate({ boldCardsEnabled })} />
        </InspectorSection>

        <InspectorSection icon={AudioLines} title="Audio">
          <SettingToggle icon={AudioLines} title="Normalizar volumen" description="Equilibra el volumen final mediante EBU R128." checked={settings.normalizeAudio} disabled={busy} onCheckedChange={(normalizeAudio) => onUpdate({ normalizeAudio })} />
        </InspectorSection>
        {children}
      </div>
    </ScrollArea>
  )
}
