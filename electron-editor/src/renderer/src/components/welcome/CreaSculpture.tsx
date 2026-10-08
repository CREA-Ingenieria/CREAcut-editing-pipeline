import { useEffect, useRef, type PointerEvent } from 'react'
import { CreaMorphLogo } from '../CreaMorphLogo'

/** Pointer coordinates come from the stationary stage, never the moving logo. */
export function CreaSculpture(): React.JSX.Element {
  const stageRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<number | null>(null)
  const reducedRef = useRef(false)

  function reset(): void {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    const stage = stageRef.current
    if (!stage) return
    stage.dataset.magnetic = 'false'
    stage.style.setProperty('--pointer-x', '0')
    stage.style.setProperty('--pointer-y', '0')
  }

  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    let inView = true
    function update(): void {
      reducedRef.current = preference.matches
      stage!.dataset.running = String(inView && !document.hidden && !preference.matches)
      if (preference.matches || document.hidden || !inView) reset()
    }
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting
      update()
    })
    observer.observe(stage)
    preference.addEventListener('change', update)
    document.addEventListener('visibilitychange', update)
    update()
    return () => {
      observer.disconnect()
      preference.removeEventListener('change', update)
      document.removeEventListener('visibilitychange', update)
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [])

  function follow(event: PointerEvent<HTMLDivElement>): void {
    if (reducedRef.current || event.pointerType === 'touch') return
    const bounds = event.currentTarget.getBoundingClientRect()
    if (!bounds.width || !bounds.height) return
    const x = Math.max(-1, Math.min(1, (event.clientX - bounds.left) / bounds.width * 2 - 1))
    const y = Math.max(-1, Math.min(1, (event.clientY - bounds.top) / bounds.height * 2 - 1))
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null
      const stage = stageRef.current
      if (!stage) return
      stage.dataset.magnetic = 'true'
      stage.style.setProperty('--pointer-x', String(x))
      stage.style.setProperty('--pointer-y', String(y))
    })
  }

  return (
    <div className="crea-sculpture" ref={stageRef} onPointerMove={follow} onPointerLeave={reset} onPointerCancel={reset}>
      <div className="crea-sculpture__grid" aria-hidden />
      <div className="crea-sculpture__orbit" aria-hidden />
      <div className="crea-sculpture__shadow" aria-hidden />
      <div className="crea-sculpture__magnet">
        <div className="crea-sculpture__float">
          <CreaMorphLogo className="crea-sculpture__wordmark" />
        </div>
      </div>
      <div className="crea-sculpture__satellites" aria-hidden>
        <i className="crea-sculpture__shape crea-sculpture__shape--circle" />
        <i className="crea-sculpture__shape crea-sculpture__shape--diamond" />
        <i className="crea-sculpture__shape crea-sculpture__shape--square" />
        <i className="crea-sculpture__shape crea-sculpture__shape--triangle" />
      </div>
      <span className="crea-sculpture__coordinate" aria-hidden>C / R / E / A</span>
      <p className="crea-sculpture__hint">Mueve el cursor. Transforma las letras.</p>
    </div>
  )
}
