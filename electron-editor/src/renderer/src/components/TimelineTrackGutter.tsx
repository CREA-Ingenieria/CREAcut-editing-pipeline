import type { LucideIcon } from 'lucide-react'
import { AudioLines, Film, Presentation, Scissors, Sparkles } from 'lucide-react'
import { TIMELINE_RULER_HEIGHT, type TimelineTrack, type TimelineTrackKey } from '../Timeline'
import { cn } from '../lib/utils'

/**
 * Columna de nombres de pista, a la izquierda del lienzo.
 *
 * Es lo que convierte una tira de bloques de colores en una línea de tiempo
 * legible: hasta ahora había que deducir qué era cada fila por su color y
 * consultar una leyenda al pie del panel. La leyenda desaparece y su
 * información pasa a estar donde se necesita, junto a la pista.
 *
 * No se desplaza con el lienzo (queda fuera del contenedor con scroll
 * horizontal), así que los nombres siguen visibles a cualquier zoom. Las
 * alturas salen de la misma función que dibuja el canvas (`timelineTracks`),
 * de modo que no pueden quedar desalineadas.
 */
interface TimelineTrackGutterProps {
  tracks: TimelineTrack[]
  height: number
  /** Color de referencia por pista, tomado de la paleta del canvas. */
  colors: Partial<Record<TimelineTrackKey, string>>
  className?: string
}

/** Ancho de la columna de nombres. Lo comparte el esqueleto de carga. */
export const TIMELINE_GUTTER_WIDTH = 112

const TRACK_ICON: Record<TimelineTrackKey, LucideIcon> = {
  video: Film,
  audio: AudioLines,
  effects: Sparkles,
  regions: Scissors,
  slides: Presentation
}

/**
 * Qué contiene cada pista y cómo se lee.
 *
 * Sustituye a la leyenda que había al pie del panel: decía qué significaban
 * los colores, pero lo decía lejos de las pistas y ocupaba una fila fija de
 * 33px que el usuario ya no leía después del primer día.
 */
const TRACK_HINT: Record<TimelineTrackKey, string> = {
  video: 'Fotogramas del video fuente. Arrastra sobre esta pista para mover el cabezal.',
  audio: 'Forma de onda del audio original.',
  effects: 'Filtros con duración. Arrastra el bloque para moverlo o sus extremos para recortarlo.',
  regions: 'Decisiones de corte: relleno liso = conservado, trama diagonal = descartado. El borde amarillo marca la región seleccionada.',
  slides: 'Diapositivas colocadas en la línea de tiempo. Contorno punteado = desactivada.'
}

export function TimelineTrackGutter({
  tracks,
  height,
  colors,
  className
}: TimelineTrackGutterProps): React.JSX.Element {
  return (
    <div
      className={cn('relative shrink-0 select-none border-r border-border bg-card', className)}
      style={{ height, width: TIMELINE_GUTTER_WIDTH }}
    >
      {/* Hueco de la regla: deja el número de la primera marca sin tapar. */}
      <div
        className="absolute inset-x-0 top-0 flex items-center border-b border-border px-2.5"
        style={{ height: TIMELINE_RULER_HEIGHT }}
      >
        <span className="panel-eyebrow">Pistas</span>
      </div>
      {tracks.map((track) => {
        const Icon = TRACK_ICON[track.key]
        return (
          <div
            key={track.key}
            title={TRACK_HINT[track.key]}
            className="absolute inset-x-0 flex items-center gap-1.5 px-2.5"
            style={{ top: track.top, height: track.height }}
          >
            <span
              className="h-3.5 w-[3px] shrink-0 rounded-full"
              style={{ background: colors[track.key] ?? 'var(--muted-2)' }}
            />
            <Icon size={12} className="shrink-0 text-muted-foreground" />
            <span className="truncate text-[10px] font-semibold tracking-tight text-foreground/75">
              {track.label}
            </span>
          </div>
        )
      })}
    </div>
  )
}
