/**
 * Reglas puras del apilado de tarjetas de la galería de proyectos.
 *
 * No depende de React ni del DOM: recibe las medidas de la pila y devuelve
 * dónde se fija cada tarjeta, en qué tramo del scroll y cuánto se encoge.
 * `useProjectStack` mide y escribe el resultado como variables CSS; el
 * navegador hace el resto con `position: sticky` y una animación ligada al
 * scroll (ver `project-portfolio.css`).
 *
 * Modelo
 * ------
 * Cada ranura, menos la última, es una "pista": se alarga lo que dura su tramo
 * (`trackHeight`) y lo devuelve con un margen negativo (`trackMargin`), así que
 * las ranuras siguientes y el largo de la página no se mueven. Dentro de esa
 * pista la tarjeta queda fija a `top` px del borde superior desde que el scroll
 * llega a `start` hasta `end`, cuando la última tarjeta alcanza su sitio y la
 * pila sale de la pantalla junta.
 */

/** Distancia desde el borde superior de la ventana a la primera tarjeta fija. */
export const STACK_TOP = 72
/** Aire que se deja bajo la tarjeta más alta al calcular el escalonado. */
export const STACK_BOTTOM_GAP = 24
/** Escalonado máximo entre tarjetas fijas, en px. */
export const STACK_MAX_STEP = 28
/** Cuánto se encoge una tarjeta por cada tarjeta que queda encima. */
export const STACK_SCALE_STEP = 0.03
/** Escala mínima de una tarjeta apilada. */
export const STACK_MIN_SCALE = 0.79

export interface StackMeasurements {
  viewportHeight: number
  /** Posición de cada ranura en el documento, sin apilar. */
  slotTops: number[]
  slotHeights: number[]
  /** Margen inferior natural de cada ranura. */
  slotMargins: number[]
  /** Borde inferior de la pila en el documento. */
  stackBottom: number
}

export interface StackedSlot {
  /** Distancia al borde superior de la ventana mientras la tarjeta está fija. */
  top: number
  /** Scroll en que la tarjeta se fija. */
  start: number
  /** Escala que alcanza al final del tramo. */
  scale: number
  trackHeight: number
  trackMargin: number
}

export interface StackLayout {
  step: number
  /** Scroll en que la última tarjeta llega a su sitio y todas se sueltan. */
  end: number
  /** Una entrada por ranura, menos la última, que nunca se fija. */
  slots: StackedSlot[]
}

export function computeStackLayout(measurements: StackMeasurements): StackLayout | null {
  const { viewportHeight, slotTops, slotHeights, slotMargins, stackBottom } = measurements
  const count = slotTops.length
  if (count < 2) return null

  const tallest = Math.max(...slotHeights)
  const step = Math.min(STACK_MAX_STEP, Math.max(0,
    (viewportHeight - tallest - STACK_TOP - STACK_BOTTOM_GAP) / (count - 1)
  ))
  const end = stackBottom - (STACK_TOP + (count - 1) * step + slotHeights[count - 1])

  const slots = slotTops.slice(0, -1).map((slotTop, index): StackedSlot => {
    const top = STACK_TOP + index * step
    const start = slotTop - top
    const pinned = Math.max(0, end - start)
    return {
      top,
      start,
      scale: Math.max(STACK_MIN_SCALE, 1 - (count - 1 - index) * STACK_SCALE_STEP),
      trackHeight: slotHeights[index] + pinned,
      trackMargin: slotMargins[index] - pinned
    }
  })

  return { step, end, slots }
}
