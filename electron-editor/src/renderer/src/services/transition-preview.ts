import type { ProjectRenderSettings } from '../../../shared/contracts'

/**
 * Reglas puras de la previsualización de transiciones.
 *
 * No depende de React ni del DOM: recibe los puntos de corte y el
 * reloj de la edición y decide qué debe verse. Así la regla se puede razonar
 * (y probar) sin montar el reproductor.
 *
 * Qué se está aproximando
 * -----------------------
 * El render real hace una fusión verdadera entre dos clips: durante la
 * transición ambos avanzan a la vez. En la previsualización solo hay **un**
 * elemento `<video>`, que no puede reproducir dos tramos del archivo
 * simultáneamente. La aproximación consiste en congelar el último fotograma del
 * corte saliente y animar esa imagen fija sobre el corte entrante, que sí sigue
 * reproduciéndose.
 *
 * La diferencia se nota únicamente si hay mucho movimiento en el clip saliente
 * durante la transición, y solo dura lo que dure la propia transición. A cambio
 * no hace falta un segundo decodificador ni pedirle nada al backend: los puntos
 * de corte (`preview.cutPointsS`) ya vienen en el contrato.
 *
 * Los cinco estilos salen de esa misma capa congelada, por eso no hay un
 * mecanismo distinto por cada uno.
 */

/**
 * Margen antes del corte en el que se captura el fotograma saliente.
 *
 * Tiene que ser mayor que el intervalo entre eventos `timeupdate` del elemento
 * `<video>`, que Chromium emite cada 60-250 ms: si fuese más corto, un corte
 * podría cruzarse sin que ninguna lectura del reloj cayera dentro de la ventana
 * y la transición se quedaría sin imagen que animar.
 */
export const FREEZE_LEAD_S = 0.35

export interface TransitionCue {
  /** Punto de corte, en tiempo editado, al que pertenece esta transición. */
  cutTimeS: number
  /** Avance dentro de la transición, de 0 (en el corte) a 1 (terminada). */
  progress: number
}

/**
 * Rectángulo que ocupa realmente la imagen dentro del reproductor.
 *
 * El `<video>` se dibuja con `object-contain`, así que su contenido casi nunca
 * llena el elemento: quedan franjas negras a los lados o arriba. La capa
 * congelada tiene que colocarse sobre ese rectángulo y no sobre el elemento
 * entero, o quedaría desalineada respecto a lo que se está viendo.
 */
export interface VideoFrameRect {
  left: number
  top: number
  width: number
  height: number
}

export interface TransitionVisual {
  /** Capa con el fotograma saliente congelado. */
  outgoing: { opacity: number; transform: string; clipPath: string }
  /** Desplazamiento del clip entrante; solo lo usa `slide_left`. */
  incoming: { transform: string }
  /** Opacidad de la capa negra; solo la usa `fade_black`. */
  blackout: number
}

/** Ancho visible de la imagen, o 0 si todavía no se ha podido medir. */
function contentWidth(frame: VideoFrameRect | null): number {
  return frame?.width ?? 0
}

/** Cierto si el estilo y la duración configurados producen alguna transición. */
export function transitionsEnabled(settings: ProjectRenderSettings): boolean {
  return settings.transitionType !== 'cut' && settings.crossfadeS > 0
}

/**
 * Punto de corte cuyo fotograma saliente conviene capturar ahora.
 *
 * Devuelve el corte que está justo por delante del cabezal, dentro del margen
 * de captura. Fuera de esa ventana devuelve `null`.
 */
export function pendingFreezeCut(
  cutPointsS: number[],
  editTimeS: number,
  leadS: number = FREEZE_LEAD_S
): number | null {
  for (const cutTimeS of cutPointsS) {
    if (editTimeS >= cutTimeS - leadS && editTimeS < cutTimeS) return cutTimeS
  }
  return null
}

/**
 * Transición activa en el instante dado, si la hay.
 *
 * La transición arranca **en** el corte y avanza hacia adelante, no centrada en
 * él: el fotograma saliente ya está congelado y lo que queda por hacer es
 * retirarlo sobre el clip entrante.
 */
export function transitionCueAt(
  cutPointsS: number[],
  editTimeS: number,
  durationS: number
): TransitionCue | null {
  if (durationS <= 0) return null
  for (const cutTimeS of cutPointsS) {
    if (editTimeS >= cutTimeS && editTimeS < cutTimeS + durationS) {
      return { cutTimeS, progress: (editTimeS - cutTimeS) / durationS }
    }
  }
  return null
}

const NEUTRAL: TransitionVisual = {
  outgoing: { opacity: 0, transform: 'none', clipPath: 'none' },
  incoming: { transform: 'none' },
  blackout: 0
}

/**
 * Traduce el avance de la transición a la geometría de las dos capas.
 *
 * `progress` se recorta a [0, 1] porque el reloj del video puede entregar
 * lecturas ligeramente fuera de rango al final de un clip.
 */
export function transitionVisual(
  kind: ProjectRenderSettings['transitionType'],
  progress: number,
  frame: VideoFrameRect | null = null
): TransitionVisual {
  const p = Math.min(1, Math.max(0, progress))

  switch (kind) {
    case 'dissolve':
      return { ...NEUTRAL, outgoing: { opacity: 1 - p, transform: 'none', clipPath: 'none' } }

    case 'fade_black':
      // Dos mitades: la primera funde el corte saliente a negro, la segunda
      // abre desde negro sobre el entrante. Por eso el fotograma congelado
      // desaparece en el punto medio en lugar de desvanecerse en toda la curva.
      return {
        ...NEUTRAL,
        outgoing: { opacity: p < 0.5 ? 1 : 0, transform: 'none', clipPath: 'none' },
        blackout: p < 0.5 ? p * 2 : (1 - p) * 2
      }

    case 'wipe_left':
      // El recorte crece por el borde derecho, así que el clip entrante se
      // descubre de derecha a izquierda. El entrante no se mueve: es el
      // saliente el que deja de taparlo.
      return {
        ...NEUTRAL,
        outgoing: { opacity: 1, transform: 'none', clipPath: `inset(0 ${p * 100}% 0 0)` }
      }

    case 'slide_left': {
      // Los dos clips se desplazan a la vez. Si solo se moviera el saliente, el
      // entrante se quedaría quieto en el centro y se verían las dos imágenes
      // separadas, como si el video estuviera duplicado.
      //
      // El desplazamiento va en píxeles del ancho **visible**, no en
      // porcentaje del elemento: con `object-contain` el elemento es más ancho
      // que la imagen, y un 100 % de elemento dejaría un hueco negro entre los
      // dos clips justo en mitad del movimiento.
      const width = contentWidth(frame)
      return {
        ...NEUTRAL,
        outgoing: { opacity: 1, transform: `translateX(${-p * width}px)`, clipPath: 'none' },
        incoming: { transform: `translateX(${(1 - p) * width}px)` }
      }
    }

    case 'cut':
    default:
      return NEUTRAL
  }
}

/**
 * Mide el rectángulo que ocupa la imagen dentro del elemento de video.
 *
 * Replica la regla de `object-contain`: la imagen se amplía hasta tocar el lado
 * que primero se llena, conservando su proporción, y se centra en el resto.
 */
export function videoFrameRect(
  elementWidth: number,
  elementHeight: number,
  videoWidth: number,
  videoHeight: number
): VideoFrameRect | null {
  if (elementWidth <= 0 || elementHeight <= 0 || videoWidth <= 0 || videoHeight <= 0) return null
  const ratio = videoWidth / videoHeight
  const width = Math.min(elementWidth, elementHeight * ratio)
  const height = width / ratio
  return {
    left: (elementWidth - width) / 2,
    top: (elementHeight - height) / 2,
    width,
    height
  }
}
