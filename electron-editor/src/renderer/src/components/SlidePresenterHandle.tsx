import { useEffect, useState } from 'react'
import type { SlidePage } from '../../../shared/contracts'

/**
 * Recorte real del presentador (PNG transparente, ya ajustado por Python a
 * su proporción real) sobre la vista previa de la diapositiva. Se puede
 * mover desde cualquier punto de la imagen y redimensionar agarrando
 * cualquiera de sus cuatro esquinas -- igual que una imagen en un editor de
 * documentos. Todo el arrastre es una reposición/reescalado local por CSS
 * (sin pedirle nada a Python en cada movimiento); solo al soltar se
 * confirma contra el proyecto.
 */
export interface PresenterBox {
  x: number
  y: number
  speakerWidth: number
  heightFraction: number
}

interface SlidePresenterHandleProps {
  containerRef: React.RefObject<HTMLDivElement | null>
  presenterUrl: string
  page: SlidePage
  disabled: boolean
  onCommit: (box: PresenterBox) => void
}

type Corner = 'nw' | 'ne' | 'sw' | 'se'

const MIN_SIZE = 0.02
const HANDLE_OFFSET = -6

function boxOf(page: SlidePage): PresenterBox {
  return { x: page.x, y: page.y, speakerWidth: page.speakerWidth, heightFraction: page.heightFraction }
}

function boxesMatch(a: PresenterBox, b: PresenterBox): boolean {
  return (
    Math.abs(a.x - b.x) < 0.001 &&
    Math.abs(a.y - b.y) < 0.001 &&
    Math.abs(a.speakerWidth - b.speakerWidth) < 0.001 &&
    Math.abs(a.heightFraction - b.heightFraction) < 0.001
  )
}

// Arrastrar una esquina mueve solo esa esquina; la opuesta queda fija --
// igual que redimensionar una imagen en Word.
function resizeFromCorner(corner: Corner, original: PresenterBox, dxFraction: number, dyFraction: number): PresenterBox {
  let left = original.x
  let top = original.y
  let right = original.x + original.speakerWidth
  let bottom = original.y + original.heightFraction
  if (corner === 'nw' || corner === 'sw') left = Math.min(1, right - MIN_SIZE, Math.max(-1, right - 1, left + dxFraction))
  if (corner === 'ne' || corner === 'se') right = Math.max(left + MIN_SIZE, Math.min(left + 1, right + dxFraction))
  if (corner === 'nw' || corner === 'ne') top = Math.min(1, bottom - MIN_SIZE, Math.max(-1, bottom - 1, top + dyFraction))
  if (corner === 'sw' || corner === 'se') bottom = Math.max(top + MIN_SIZE, Math.min(top + 1, bottom + dyFraction))
  return { x: left, y: top, speakerWidth: right - left, heightFraction: bottom - top }
}

// El origen puede cruzar el borde. No se resta el tamaño de la caja:
// el visor recorta el excedente y el separador se dibuja por encima.
function moveBox(original: PresenterBox, dxFraction: number, dyFraction: number): PresenterBox {
  const x = Math.min(1, Math.max(-1, original.x + dxFraction))
  const y = Math.min(1, Math.max(-1, original.y + dyFraction))
  return { ...original, x, y }
}

function cornerStyle(corner: Corner): React.CSSProperties {
  const style: React.CSSProperties = {}
  if (corner === 'nw' || corner === 'sw') style.left = HANDLE_OFFSET
  else style.right = HANDLE_OFFSET
  if (corner === 'nw' || corner === 'ne') style.top = HANDLE_OFFSET
  else style.bottom = HANDLE_OFFSET
  style.cursor = corner === 'nw' || corner === 'se' ? 'nwse-resize' : 'nesw-resize'
  return style
}

export function SlidePresenterHandle({
  containerRef,
  presenterUrl,
  page,
  disabled,
  onCommit
}: SlidePresenterHandleProps): React.JSX.Element | null {
  const [action, setAction] = useState<{
    kind: 'move' | 'resize'
    corner?: Corner
    startX: number
    startY: number
    original: PresenterBox
    current: PresenterBox
    // true once the pointer is released and the commit is in flight: the
    // box stays pinned where it was left until `page` (the prop) catches
    // up, instead of snapping back to the old value during the round trip.
    pending: boolean
  } | null>(null)

  useEffect(() => {
    // Al terminar la petición también se descarta la posición optimista si
    // el guardado falló, para volver a mostrar la geometría persistida.
    if (action?.pending && (!disabled || boxesMatch(action.current, boxOf(page)))) setAction(null)
  }, [action, disabled, page.x, page.y, page.speakerWidth, page.heightFraction])

  // Cada diapositiva tiene su propia caja independiente: si se cambia de
  // diapositiva a mitad de una acción pendiente, ese estado local no debe
  // arrastrarse a la diapositiva nueva.
  useEffect(() => {
    setAction(null)
  }, [page.id])

  const box = action ? action.current : boxOf(page)

  function localPointer(event: React.PointerEvent): { x: number; y: number } | null {
    const bounds = containerRef.current?.getBoundingClientRect()
    if (!bounds?.width || !bounds.height) return null
    return { x: (event.clientX - bounds.left) / bounds.width, y: (event.clientY - bounds.top) / bounds.height }
  }

  function start(kind: 'move' | 'resize', corner: Corner | undefined, event: React.PointerEvent): void {
    if (disabled) return
    const pointer = localPointer(event)
    if (!pointer) return
    event.preventDefault()
    event.stopPropagation()
    event.currentTarget.setPointerCapture(event.pointerId)
    const original = boxOf(page)
    setAction({ kind, corner, startX: pointer.x, startY: pointer.y, original, current: original, pending: false })
  }

  function move(event: React.PointerEvent): void {
    if (!action || action.pending) return
    const pointer = localPointer(event)
    if (!pointer) return
    const dx = pointer.x - action.startX
    const dy = pointer.y - action.startY
    const current =
      action.kind === 'move'
        ? moveBox(action.original, dx, dy)
        : resizeFromCorner(action.corner!, action.original, dx, dy)
    setAction({ ...action, current })
  }

  function finish(event: React.PointerEvent): void {
    if (!action) return
    event.currentTarget.releasePointerCapture(event.pointerId)
    if (boxesMatch(action.current, action.original)) {
      setAction(null)
      return
    }
    onCommit(action.current)
    setAction({ ...action, pending: true })
  }

  return (
    <div
      className="presenter-layer absolute z-[4]"
      data-presenter-layer
      data-active={action && !action.pending ? 'true' : 'false'}
      style={{
        left: `${box.x * 100}%`,
        top: `${box.y * 100}%`,
        width: `${box.speakerWidth * 100}%`,
        height: `${box.heightFraction * 100}%`
      }}
    >
      {/* Contorno como hermano y no como `outline` de la imagen: durante el
          arrastre la caja se mueve píxel a píxel y el contorno tiene que ir
          exactamente con ella, sin recalcular el trazado del PNG. */}
      <span aria-hidden className="presenter-layer__frame pointer-events-none absolute -inset-px rounded-sm" />
      <img
        src={presenterUrl}
        alt="Presentador"
        draggable={false}
        className="relative h-full w-full select-none"
        style={{ cursor: disabled ? 'not-allowed' : 'move', touchAction: 'none' }}
        title={disabled ? undefined : 'Arrastra para mover; agarra una esquina para cambiar el tamaño'}
        onPointerDown={(event) => start('move', undefined, event)}
        onPointerMove={move}
        onPointerUp={finish}
        onPointerCancel={() => setAction(null)}
      />
      {!disabled &&
        (['nw', 'ne', 'sw', 'se'] as const).map((corner) => (
          <div
            key={corner}
            role="presentation"
            aria-label={`Redimensionar desde la esquina ${corner}`}
            className="presenter-layer__handle absolute h-2.5 w-2.5 rounded-full border-2 border-[color:var(--color-primary)] bg-white shadow-sm"
            style={{ ...cornerStyle(corner), touchAction: 'none' }}
            onPointerDown={(event) => start('resize', corner, event)}
            onPointerMove={move}
            onPointerUp={finish}
            onPointerCancel={() => setAction(null)}
          />
        ))}
    </div>
  )
}
