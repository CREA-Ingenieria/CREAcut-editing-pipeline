import type { TransitionVisual, VideoFrameRect } from '../services/transition-preview'

/**
 * Las dos capas de la transición, sobre el video.
 *
 * El `<canvas>` está siempre montado aunque no haya transición: es donde
 * `useTransitionPreview` vuelca el fotograma saliente **antes** de que el corte
 * ocurra, así que desmontarlo entre transiciones destruiría justo la imagen que
 * hace falta un instante después. Lo que cambia es su opacidad.
 *
 * El canvas no se estira al elemento entero, sino al rectángulo que ocupa
 * realmente la imagen. Con `object-contain` el `<video>` deja franjas negras a
 * los lados, y una capa a pantalla completa quedaría desalineada respecto a lo
 * que se está viendo — y el recorte del barrido cortaría por el sitio
 * equivocado.
 *
 * `pointer-events-none` en ambas capas: son decorado sobre el reproductor y no
 * deben interceptar clics dirigidos al video.
 */
interface TransitionOverlayProps {
  canvasRef: React.RefObject<HTMLCanvasElement>
  /** Geometría calculada por `useTransitionPreview`, o `null` sin transición. */
  visual: TransitionVisual | null
  frame: VideoFrameRect | null
}

export function TransitionOverlay({
  canvasRef,
  visual,
  frame
}: TransitionOverlayProps): React.JSX.Element {
  return (
    <>
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="pointer-events-none absolute z-[2]"
        style={{
          left: frame?.left ?? 0,
          top: frame?.top ?? 0,
          width: frame?.width ?? '100%',
          height: frame?.height ?? '100%',
          opacity: visual ? visual.outgoing.opacity : 0,
          transform: visual?.outgoing.transform ?? 'none',
          clipPath: visual?.outgoing.clipPath ?? 'none'
        }}
      />
      {visual && visual.blackout > 0 && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-[2] bg-black"
          style={{ opacity: visual.blackout }}
        />
      )}
    </>
  )
}
