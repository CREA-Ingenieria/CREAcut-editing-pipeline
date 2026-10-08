import { useLayoutEffect, useState } from 'react'
import { videoFrameRect, type VideoFrameRect } from '../services/transition-preview'

/**
 * Rectángulo que ocupa realmente la imagen dentro del escenario del visor.
 *
 * Por qué hace falta
 * ------------------
 * El escenario ocupa todo el espacio libre de la columna central, así que casi
 * nunca coincide con la proporción del material: quedan franjas arriba y abajo,
 * o a los lados. Todo lo que se superpone al vídeo —el presentador de una
 * diapositiva, las etiquetas de modo y efecto, la capa congelada de la
 * transición— tiene que colocarse sobre **este** rectángulo y no sobre el
 * contenedor.
 *
 * Es lo que hace que el presentador conserve su posición relativa al vídeo
 * cuando se arrastra un separador: su caja se expresa en fracciones del
 * rectángulo de imagen, y el rectángulo se vuelve a medir con cada cambio de
 * tamaño. Anclarlo al contenedor haría que la persona «resbalase» sobre la
 * diapositiva cada vez que el usuario ensancha un panel.
 *
 * Por qué se mide y no se resuelve con CSS
 * ----------------------------------------
 * `aspect-ratio` combinado con `max-width` / `max-height` no conserva la
 * proporción en los dos sentidos: en un contenedor más ancho que alto, la caja
 * se desborda por abajo; con `height: 100%`, se desborda por la derecha en el
 * caso contrario. Comprobado en Chromium con las dos variantes. La única forma
 * fiable de encajar «contain» y además **conocer** el rectángulo resultante
 * (que es lo que necesita el presentador) es medirlo.
 *
 * Cómo se mide
 * ------------
 * Se mide al montar el contenedor. Después, `ResizeObserver` detecta cambios
 * de tamaño por paneles, ventana o CSS y agrupa la medida por fotograma.
 * No se escribe estado desde un efecto de layout en cada render: eso podía
 * encadenar actualizaciones hasta bloquear la apertura del editor.
 */
export function useMediaRect(
  containerRef: React.RefObject<HTMLElement>,
  aspectRatio: number
): VideoFrameRect | null {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return
    let pendingFrame: number | null = null
    const measure = (): void => {
      // Ignorar el transform de la animación de entrada al medir el layout.
      const width = container.clientWidth
      const height = container.clientHeight
      setSize((current) =>
        current && current.width === width && current.height === height
          ? current
          : { width, height }
      )
    }

    measure()
    const observer = new ResizeObserver(() => {
      if (pendingFrame !== null) return
      pendingFrame = requestAnimationFrame(() => {
        pendingFrame = null
        measure()
      })
    })
    observer.observe(container)
    return () => {
      observer.disconnect()
      if (pendingFrame !== null) cancelAnimationFrame(pendingFrame)
    }
  }, [containerRef])

  if (!size || aspectRatio <= 0) return null
  // `videoFrameRect` ya resuelve el encaje «contain» para la capa de
  // transición; reutilizarlo evita dos definiciones del mismo rectángulo.
  return videoFrameRect(size.width, size.height, aspectRatio * 1000, 1000)
}
