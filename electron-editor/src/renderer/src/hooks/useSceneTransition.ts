import { useEffect, useRef, useState } from 'react'

export type Scene = 'welcome' | 'editor'

/**
 * Retiene el cambio de pantalla el tiempo justo para que la que se va pueda
 * despedirse.
 *
 * El problema
 * -----------
 * `App` decide qué pantalla mostrar a partir de si hay proyecto abierto. Sin
 * nada en medio, abrir un proyecto sustituye la bienvenida por el editor en un
 * solo fotograma: dos pantallas que no comparten ningún elemento se
 * intercambian de golpe y el usuario pierde el hilo de dónde estaba.
 *
 * La solución
 * -----------
 * Este hook separa el destino (`target`, derivado del estado) de lo que se
 * pinta (`scene`). Cuando difieren, marca `leaving`, espera a que termine la
 * animación de salida y solo entonces cambia `scene`.
 *
 * Por qué escucha `animationend` en vez de usar un temporizador
 * -------------------------------------------------------------
 * Un `setTimeout` con la duración copiada de `styles.css` se desincroniza en
 * cuanto alguien ajusta la curva, y sobre todo se desincroniza con
 * `prefers-reduced-motion`, donde la animación se sustituye por un fundido más
 * corto. Escuchar el final real del evento funciona en los dos casos. El
 * temporizador que sí existe es solo una red de seguridad: si la animación
 * nunca llega a arrancar (pestaña en segundo plano, clase ausente), la pantalla
 * cambia igualmente y la aplicación no se queda encallada.
 */
const LEAVE_FALLBACK_MS = 700

export function useSceneTransition(target: Scene): {
  /** Pantalla que debe renderizarse ahora mismo. */
  scene: Scene
  /** Cierto mientras la pantalla actual reproduce su salida. */
  leaving: boolean
  /** Va en el envoltorio de la escena: es el elemento que se anima. */
  wrapRef: React.RefObject<HTMLDivElement>
} {
  const [scene, setScene] = useState<Scene>(target)
  const [leaving, setLeaving] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (target === scene) {
      setLeaving(false)
      return
    }

    setLeaving(true)
    const node = wrapRef.current
    let settled = false

    const finish = (): void => {
      if (settled) return
      settled = true
      setLeaving(false)
      setScene(target)
    }

    // Solo interesa la animación del propio envoltorio: los hijos animan lo
    // suyo (entradas de paneles, esqueletos) y no deben adelantar el cambio.
    const onEnd = (event: AnimationEvent): void => {
      if (event.target === node) finish()
    }

    node?.addEventListener('animationend', onEnd)
    const safety = window.setTimeout(finish, LEAVE_FALLBACK_MS)

    return () => {
      node?.removeEventListener('animationend', onEnd)
      window.clearTimeout(safety)
    }
  }, [target, scene])

  return { scene, leaving, wrapRef }
}
