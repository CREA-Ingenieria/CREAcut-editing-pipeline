import { useCallback, useEffect, useState } from 'react'

/**
 * Tamaños y plegado de los paneles del editor.
 *
 * Por qué existe
 * --------------
 * La versión anterior repartía la pantalla con una rejilla fija
 * (`300px 1fr 350px`) y una altura fija para la línea de tiempo. En una
 * ventana estrecha eso obligaba a desplazar la columna central para llegar a
 * la línea de tiempo — el gesto de una página web, no el de un editor. Aquí
 * los tres bordes son ajustables y cada panel puede plegarse, de modo que el
 * armazón siempre ocupa exactamente la ventana.
 *
 * Los valores se guardan en `localStorage`: el reparto de la pantalla es una
 * preferencia de trabajo, no un estado del proyecto, y volver a colocarlo en
 * cada sesión es justo el tipo de fricción que distingue una herramienta de
 * escritorio de una web.
 */
export type PanelKey = 'left' | 'right' | 'timeline'

export interface PanelBounds {
  min: number
  max: number
  initial: number
}

/**
 * Mínimos reales, no estéticos: por debajo de ellos el contenido del panel
 * deja de ser utilizable (la transcripción parte palabras, el inspector
 * apila etiqueta y control, la línea de tiempo pierde una pista entera).
 */
export const PANEL_BOUNDS: Record<PanelKey, PanelBounds> = {
  left: { min: 216, max: 460, initial: 292 },
  right: { min: 264, max: 480, initial: 336 },
  // 258 = barra de herramientas (36) + las cinco pistas dibujadas (212) + la
  // barra de desplazamiento horizontal (10), de modo que al abrir no queda ni
  // una franja vacía bajo la última pista ni una pista recortada.
  timeline: { min: 120, max: 560, initial: 258 }
}

export interface PanelLayout {
  size: Record<PanelKey, number>
  collapsed: Record<PanelKey, boolean>
  resize: (key: PanelKey, deltaPx: number) => void
  toggle: (key: PanelKey) => void
  /** Devuelve el panel a su tamaño de fábrica (doble clic en el separador). */
  reset: (key: PanelKey) => void
}

const STORAGE_KEY = 'creacut-panel-layout'

interface StoredLayout {
  size?: Partial<Record<PanelKey, number>>
  collapsed?: Partial<Record<PanelKey, boolean>>
}

function clamp(key: PanelKey, value: number): number {
  const bounds = PANEL_BOUNDS[key]
  return Math.round(Math.min(bounds.max, Math.max(bounds.min, value)))
}

function readStored(): StoredLayout {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as StoredLayout) : {}
  } catch {
    // Un `localStorage` ilegible (modo privado, cuota, JSON corrupto) no debe
    // impedir abrir el editor: se cae a los valores de fábrica.
    return {}
  }
}

export function usePanelLayout(): PanelLayout {
  const [size, setSize] = useState<Record<PanelKey, number>>(() => {
    const stored = readStored().size ?? {}
    return {
      left: clamp('left', stored.left ?? PANEL_BOUNDS.left.initial),
      right: clamp('right', stored.right ?? PANEL_BOUNDS.right.initial),
      timeline: clamp('timeline', stored.timeline ?? PANEL_BOUNDS.timeline.initial)
    }
  })
  const [collapsed, setCollapsed] = useState<Record<PanelKey, boolean>>(() => {
    const stored = readStored().collapsed ?? {}
    return {
      left: stored.left ?? false,
      right: stored.right ?? false,
      timeline: stored.timeline ?? false
    }
  })

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ size, collapsed }))
    } catch {
      // Guardar la preferencia es una comodidad; si falla, la sesión sigue.
    }
  }, [size, collapsed])

  const resize = useCallback((key: PanelKey, deltaPx: number) => {
    setSize((current) => ({ ...current, [key]: clamp(key, current[key] + deltaPx) }))
    // Arrastrar el separador de un panel plegado equivale a desplegarlo: si no,
    // el gesto no tendría ningún efecto visible y parecería que está roto.
    setCollapsed((current) => (current[key] ? { ...current, [key]: false } : current))
  }, [])

  const toggle = useCallback((key: PanelKey) => {
    setCollapsed((current) => ({ ...current, [key]: !current[key] }))
  }, [])

  const reset = useCallback((key: PanelKey) => {
    setSize((current) => ({ ...current, [key]: PANEL_BOUNDS[key].initial }))
    setCollapsed((current) => ({ ...current, [key]: false }))
  }, [])

  return { size, collapsed, resize, toggle, reset }
}
