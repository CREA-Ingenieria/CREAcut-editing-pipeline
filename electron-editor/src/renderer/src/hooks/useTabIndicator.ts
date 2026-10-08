import { useEffect, useRef } from 'react'

/**
 * Mide la pestaña activa de una lista y coloca sobre ella una única barra que
 * viaja entre pestañas.
 *
 * Por qué medir en lugar de encender un borde por pestaña
 * -------------------------------------------------------
 * Un borde que se apaga en una pestaña y se enciende en otra no dice nada: son
 * dos cambios de opacidad sin relación. Una barra que se desplaza sí explica
 * que el foco se ha movido de A a B, que es justo la lectura que se busca.
 *
 * Cómo se anima
 * -------------
 * El hook solo escribe dos variables (`--tab-x`, `--tab-w`) sobre el indicador;
 * la transición vive en `.tab-indicator` (styles.css). La posición se anima con
 * `transform`, que se resuelve en el compositor y es lo que se mueve en cada
 * fotograma.
 *
 * El ancho, en cambio, es `width` y no `scaleX`. Escalar salía más barato, pero
 * `scaleX` escala también el `box-shadow`: con una barra base de 1px estirada
 * unas 120 veces, el resplandor de 10px se convertía en una banda de ~1200px
 * que cruzaba el panel. La barra está fuera de flujo (`position: absolute`) y
 * su ancho solo cambia al saltar de pestaña, así que el reflow es intrascendente.
 *
 * Qué se observa
 * --------------
 * - `MutationObserver` sobre `data-state`: Radix marca así la pestaña activa,
 *   de modo que no hace falta duplicar aquí el estado de las pestañas.
 * - `ResizeObserver` sobre la lista: si el panel cambia de ancho, o una
 *   etiqueta pasa a ocupar dos líneas, la barra debe volver a medirse.
 *
 * La primera medida ocurre antes de pintar (`useLayoutEffect` no hace falta:
 * `data-ready` mantiene el indicador invisible hasta que hay una medida real,
 * lo que además evita ver una barra de 1px en el origen).
 */
export function useTabIndicator<T extends HTMLElement = HTMLDivElement>(): {
  listRef: React.RefObject<T>
  indicatorRef: React.RefObject<HTMLSpanElement>
} {
  const listRef = useRef<T>(null)
  const indicatorRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const list = listRef.current
    const indicator = indicatorRef.current
    if (!list || !indicator) return

    const measure = (): void => {
      const active = list.querySelector<HTMLElement>('[data-state="active"]')
      // Sin pestaña activa (o aún sin medidas) el indicador se oculta en vez
      // de quedarse encallado sobre la posición anterior.
      if (!active || active.offsetWidth === 0) {
        indicator.dataset.ready = 'false'
        return
      }
      indicator.style.setProperty('--tab-x', `${active.offsetLeft}px`)
      indicator.style.setProperty('--tab-w', `${active.offsetWidth}px`)
      indicator.dataset.ready = 'true'
    }

    measure()

    const mutations = new MutationObserver(measure)
    mutations.observe(list, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['data-state']
    })

    const resizes = new ResizeObserver(measure)
    resizes.observe(list)

    return () => {
      mutations.disconnect()
      resizes.disconnect()
    }
  }, [])

  return { listRef, indicatorRef }
}
