import { useRef, useState } from 'react'
import { cn } from '../../lib/utils'

/**
 * Separador arrastrable entre dos paneles.
 *
 * Movimiento
 * ----------
 * El arrastre **no** se anima: redimensionar es un gesto de precisión y el
 * panel tiene que ir pegado al puntero. Lo único que cambia con transición es
 * el color de la línea (120 ms), que es lo que indica que el separador está
 * bajo el cursor o en uso.
 *
 * Superficie de agarre
 * --------------------
 * La línea visible mide 1px, pero la zona sensible mide 9px y sobresale hacia
 * ambos lados sin ocupar sitio en el reparto (`position: absolute` sobre un
 * carril de 1px). Un separador de 1px es un objetivo imposible con ratón y
 * obliga a apuntar dos veces; ampliarlo visualmente engordaría todas las
 * juntas del editor.
 *
 * La zona sensible se dibuja **por debajo** del contenido de los paneles
 * (`z-0` sobre un carril propio), así que nunca recorta ni intercepta lo que
 * el lienzo del visor superponga cerca del borde.
 */
interface PanelDividerProps {
  orientation: 'vertical' | 'horizontal'
  label: string
  /** Delta en píxeles desde el último evento; el signo ya viene aplicado. */
  onResize: (deltaPx: number) => void
  /** Doble clic: devolver el panel a su tamaño de fábrica. */
  onReset?: () => void
  /** Tamaño actual y límites del panel, para los lectores de pantalla. */
  value?: { now: number; min: number; max: number }
  className?: string
}

const KEYBOARD_STEP = 16

export function PanelDivider({
  orientation,
  label,
  onResize,
  onReset,
  value,
  className
}: PanelDividerProps): React.JSX.Element {
  const lastPositionRef = useRef<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const isVertical = orientation === 'vertical'

  function positionOf(event: React.PointerEvent): number {
    return isVertical ? event.clientX : event.clientY
  }

  return (
    <div
      role="separator"
      aria-orientation={isVertical ? 'vertical' : 'horizontal'}
      aria-label={label}
      aria-valuenow={value?.now}
      aria-valuemin={value?.min}
      aria-valuemax={value?.max}
      tabIndex={0}
      data-dragging={dragging ? 'true' : 'false'}
      className={cn(
        'panel-divider group relative z-0 shrink-0 bg-border-soft outline-none',
        isVertical ? 'w-px cursor-col-resize' : 'h-px cursor-row-resize',
        className
      )}
      onPointerDown={(event) => {
        // Solo el botón principal: el secundario abre menús del sistema y un
        // arrastre iniciado con él nunca recibe su `pointerup`.
        if (event.button !== 0) return
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        lastPositionRef.current = positionOf(event)
        setDragging(true)
      }}
      onPointerMove={(event) => {
        const last = lastPositionRef.current
        if (last === null) return
        const next = positionOf(event)
        if (next === last) return
        lastPositionRef.current = next
        onResize(next - last)
      }}
      onPointerUp={(event) => {
        if (lastPositionRef.current === null) return
        event.currentTarget.releasePointerCapture(event.pointerId)
        lastPositionRef.current = null
        setDragging(false)
      }}
      onPointerCancel={() => {
        lastPositionRef.current = null
        setDragging(false)
      }}
      onDoubleClick={onReset}
      onKeyDown={(event) => {
        const back = isVertical ? 'ArrowLeft' : 'ArrowUp'
        const forward = isVertical ? 'ArrowRight' : 'ArrowDown'
        if (event.key === back) {
          event.preventDefault()
          onResize(-KEYBOARD_STEP)
        } else if (event.key === forward) {
          event.preventDefault()
          onResize(KEYBOARD_STEP)
        } else if (event.key === 'Enter' && onReset) {
          event.preventDefault()
          onReset()
        }
      }}
    >
      <span
        aria-hidden
        className={cn(
          'panel-divider__hit absolute',
          isVertical ? '-inset-x-1 inset-y-0' : '-inset-y-1 inset-x-0'
        )}
      />
    </div>
  )
}
