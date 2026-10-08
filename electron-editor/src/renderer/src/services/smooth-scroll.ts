/**
 * Desplazamiento suavizado de la pantalla de bienvenida, sobre Lenis (MIT).
 *
 * Lenis no traduce el contenido: anima el scroll nativo del documento. Por eso
 * `position: sticky`, las animaciones ligadas al scroll y el foco con teclado
 * funcionan como en cualquier página, y el apilado de proyectos no necesita
 * conocerlo.
 *
 * Este módulo es el único que importa Lenis. Mantiene una sola instancia viva:
 * la bienvenida es la única vista que se desplaza.
 */
import Lenis from 'lenis'

/** Duración de la inercia, en segundos. */
const SMOOTH_SECONDS = 2

/** Atributo con el que Radix bloquea el scroll de la página al abrir un diálogo. */
const SCROLL_LOCK_ATTRIBUTE = 'data-scroll-locked'

/** Salida exponencial: arranca rápido y se posa despacio. */
function easeOutExpo(progress: number): number {
  return progress >= 1 ? 1 : 1 - Math.pow(2, -10 * progress)
}

let active: Lenis | null = null

/**
 * Suaviza la rueda sobre `content` y devuelve la función que lo deshace.
 *
 * Los eventos que nacen fuera de `content` —los diálogos de Radix se montan en
 * un portal sobre `<body>`— y los que llegan con la página bloqueada siguen su
 * camino nativo: así el diálogo se desplaza por dentro y la página queda quieta.
 * `allowNestedScroll` deja que las cajas con scroll propio (los errores de una
 * tarjeta) se desplacen solas.
 */
export function createSmoothScroll(content: HTMLElement): () => void {
  const lenis = new Lenis({
    duration: SMOOTH_SECONDS,
    easing: easeOutExpo,
    autoRaf: true,
    allowNestedScroll: true,
    virtualScroll: ({ event }) => {
      if (document.body.hasAttribute(SCROLL_LOCK_ATTRIBUTE)) return false
      return event.target instanceof Node && content.contains(event.target)
    }
  })
  active = lenis
  return () => {
    lenis.destroy()
    if (active === lenis) active = null
  }
}

/** Salta a `top` sin animación, haya o no suavizado activo. */
export function scrollToImmediate(top: number): void {
  if (active) active.scrollTo(top, { immediate: true, force: true })
  else window.scrollTo({ top, behavior: 'instant' })
}
