import { useEffect, useRef } from 'react'
import { computeStackLayout } from '../services/project-stack-motion'
import { scrollToImmediate } from '../services/smooth-scroll'

/** Ventana grande y sin reducción de movimiento: fuera de eso, las tarjetas van una debajo de otra. */
const STACK_QUERY = '(min-width: 850px) and (min-height: 700px) and (prefers-reduced-motion: no-preference)'

/** Clase que activa las reglas de apilado de `project-portfolio.css`. */
const STACKED_CLASS = 'is-stacked'

const STACK_VARIABLES = [
  '--stack-top', '--stack-start', '--stack-end', '--stack-scale', '--stack-track-height', '--stack-track-margin'
] as const

/** Pin the outer slots; scale their inner cards. The browser does both with
 * `position: sticky` and a scroll-driven animation; this hook only measures. */
export function useProjectStack(signature: string) {
  const stackRef = useRef<HTMLDivElement>(null)
  const startsRef = useRef<number[]>([])
  const keyboardFocusRef = useRef(false)

  useEffect(() => {
    const pointer = (): void => { keyboardFocusRef.current = false }
    const keyboard = (event: KeyboardEvent): void => {
      if (event.key === 'Tab') keyboardFocusRef.current = true
    }
    // Capture before the browser focuses a button on pointerdown. Focus alone
    // must not move a card out from under the pointer before the click fires.
    window.addEventListener('pointerdown', pointer, true)
    window.addEventListener('keydown', keyboard, true)
    return () => {
      window.removeEventListener('pointerdown', pointer, true)
      window.removeEventListener('keydown', keyboard, true)
    }
  }, [])

  useEffect(() => {
    const stack = stackRef.current
    if (!stack) return
    const media = window.matchMedia(STACK_QUERY)
    let release: (() => void) | null = null
    const sync = (): void => {
      release?.()
      release = media.matches ? stackCards(stack, startsRef) : null
    }
    sync()
    media.addEventListener('change', sync)
    return () => {
      media.removeEventListener('change', sync)
      release?.()
    }
  }, [signature])

  function revealFocusedCard(index: number): void {
    if (!keyboardFocusRef.current) return
    const start = startsRef.current[index]
    if (start === undefined) return
    scrollToImmediate(start)
  }

  return { stackRef, revealFocusedCard }
}

/** Posición en el documento sin transformaciones: `offsetTop` las ignora. */
function documentTop(element: HTMLElement): number {
  let top = 0
  for (let node: HTMLElement | null = element; node; node = node.offsetParent as HTMLElement | null) {
    top += node.offsetTop
  }
  return top
}

/** Activa el apilado y devuelve cómo deshacerlo, o `null` si no hay qué apilar. */
function stackCards(stack: HTMLElement, startsRef: { current: number[] }): (() => void) | null {
  const slots = Array.from(stack.querySelectorAll<HTMLElement>('[data-project-slot]'))
  if (slots.length < 2) return null
  let frame = 0

  const clear = (): void => {
    stack.classList.remove(STACKED_CLASS)
    for (const slot of slots) for (const name of STACK_VARIABLES) slot.style.removeProperty(name)
    startsRef.current = []
  }

  const measure = (): void => {
    frame = 0
    // Se mide sin apilar: así las alturas y los márgenes son los naturales. La
    // clase se quita y se vuelve a poner en la misma tarea, sin pintar entre medias.
    stack.classList.remove(STACKED_CLASS)
    const layout = computeStackLayout({
      viewportHeight: window.innerHeight,
      slotTops: slots.map(documentTop),
      slotHeights: slots.map((slot) => slot.offsetHeight),
      slotMargins: slots.map((slot) => parseFloat(getComputedStyle(slot).marginBottom) || 0),
      stackBottom: documentTop(stack) + stack.offsetHeight
    })
    if (!layout) return clear()
    layout.slots.forEach((stacked, index) => {
      const style = slots[index].style
      style.setProperty('--stack-top', `${stacked.top}px`)
      style.setProperty('--stack-start', `${stacked.start}px`)
      style.setProperty('--stack-end', `${layout.end}px`)
      style.setProperty('--stack-scale', String(stacked.scale))
      style.setProperty('--stack-track-height', `${stacked.trackHeight}px`)
      style.setProperty('--stack-track-margin', `${stacked.trackMargin}px`)
    })
    startsRef.current = layout.slots.map((stacked) => stacked.start)
    stack.classList.add(STACKED_CLASS)
  }

  // Las vistas previas cambian la altura de las tarjetas al cargar y el héroe
  // puede crecer con un aviso: se vuelve a medir, como mucho una vez por fotograma.
  // Se observa cada tarjeta, no solo la pila: mientras está apilada, la pista
  // tiene un alto fijo y la pila no cambia aunque la tarjeta crezca.
  const schedule = (): void => { if (!frame) frame = requestAnimationFrame(measure) }
  const observer = new ResizeObserver(schedule)
  observer.observe(stack)
  observer.observe(document.body)
  for (const slot of slots) observer.observe(slot.querySelector<HTMLElement>('[data-project-card]') ?? slot)
  window.addEventListener('resize', schedule)
  measure()

  return () => {
    observer.disconnect()
    window.removeEventListener('resize', schedule)
    cancelAnimationFrame(frame)
    clear()
  }
}
