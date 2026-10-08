/**
 * Desplazamiento suavizado de la pantalla de bienvenida.
 *
 * Qué resuelve
 * ------------
 * El suavizado (ver `services/smooth-scroll.ts`) anima el scroll del documento,
 * así que **necesita que el documento sea el elemento desplazable**.
 *
 * Eso choca con `html, body, #root { overflow: hidden }` de `styles.css`, que
 * existe para que el editor ocupe exactamente la ventana. En vez de relajar esa
 * regla globalmente —lo que afectaría a `EditorView`, donde el desplazamiento de
 * página sería un error— este hook pone la clase `welcome-smooth` en `<html>`
 * mientras la bienvenida está montada y la quita al desmontarla. El bloque de
 * `styles.css` que responde a esa clase es la única excepción.
 *
 * Diálogos
 * --------
 * Los diálogos de Radix (crear proyecto, lote, progreso) se montan en un portal
 * sobre `<body>`, fuera del contenido. Sus eventos de rueda no se suavizan, y
 * mientras Radix bloquea la página tampoco: el diálogo se desplaza por dentro y
 * la página queda congelada, que es el comportamiento deseado.
 *
 * Accesibilidad
 * -------------
 * Con `prefers-reduced-motion: reduce` no se crea el suavizado: la página se
 * desplaza de forma nativa y todo el contenido sigue siendo accesible. El foco
 * con teclado lo desplaza el navegador, como en cualquier página.
 */
import { useEffect, type RefObject } from 'react'
import 'lenis/dist/lenis.css'
import { createSmoothScroll } from '../services/smooth-scroll'

/** Clase que libera el bloqueo de desplazamiento del documento. */
const SCROLL_MODE_CLASS = 'welcome-smooth'

interface SmoothScrollerOptions {
  contentRef: RefObject<HTMLElement | null>
}

export function useSmoothScroller({ contentRef }: SmoothScrollerOptions): void {
  useEffect(() => {
    const content = contentRef.current
    if (!content) return

    const root = document.documentElement
    root.classList.add(SCROLL_MODE_CLASS)

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const destroy = reducedMotion ? null : createSmoothScroll(content)

    return () => {
      destroy?.()
      root.classList.remove(SCROLL_MODE_CLASS)
      window.scrollTo(0, 0)
    }
  }, [contentRef])
}
