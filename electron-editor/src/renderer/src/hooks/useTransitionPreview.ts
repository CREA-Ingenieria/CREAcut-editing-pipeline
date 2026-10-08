import { useEffect, useRef, useState } from 'react'
import type { ProjectView } from '../../../shared/contracts'
import {
  pendingFreezeCut,
  transitionCueAt,
  transitionsEnabled,
  transitionVisual,
  videoFrameRect,
  type TransitionCue,
  type TransitionVisual,
  type VideoFrameRect
} from '../services/transition-preview'

/**
 * Captura el fotograma saliente de cada corte y expone la transición activa.
 *
 * Reparto de responsabilidades: las reglas de cuándo hay transición y qué
 * geometría le toca viven en `services/transition-preview.ts`; aquí queda solo
 * lo imperativo, que es hablar con el elemento `<video>` y con un `<canvas>`.
 *
 * El ciclo, por cada corte:
 *
 *   1. el cabezal entra en la ventana previa al corte y el clip saliente
 *      todavía se está reproduciendo → se vuelca ese fotograma al canvas;
 *   2. el reproductor salta al clip siguiente al llegar al corte;
 *   3. mientras dura la transición, la capa del canvas se retira encima del
 *      clip entrante siguiendo el estilo configurado.
 *
 * Por qué se captura antes y no en el corte
 * -----------------------------------------
 * En el instante del corte el `<video>` ya muestra el clip **entrante**:
 * capturar ahí congelaría la imagen equivocada. La ventana previa es el único
 * momento en que el fotograma saliente sigue en pantalla.
 *
 * Solo se activa durante la reproducción en modo previsualización. Al arrastrar
 * el cabezal no hay transición que mostrar: el usuario está buscando un
 * instante, y una capa animada encima solo estorbaría.
 */
interface TransitionPreviewOptions {
  project: ProjectView
  videoRef: React.RefObject<HTMLVideoElement>
  /** Tiempo en el reloj de la edición, o `null` fuera de la edición. */
  editTimeS: number | null
  active: boolean
}

interface TransitionPreview {
  canvasRef: React.RefObject<HTMLCanvasElement>
  cue: TransitionCue | null
  /** Rectángulo que ocupa la imagen dentro del reproductor. */
  frame: VideoFrameRect | null
  /**
   * Geometría de las dos capas, o `null` si ahora mismo no hay transición.
   *
   * Se calcula aquí y no en cada componente porque la usan dos: el overlay
   * mueve la capa saliente y el propio `<video>` la entrante. Duplicar el
   * cálculo abriría la puerta a que se desincronicen.
   */
  visual: TransitionVisual | null
}

export function useTransitionPreview({
  project,
  videoRef,
  editTimeS,
  active
}: TransitionPreviewOptions): TransitionPreview {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const capturedCutRef = useRef<number | null>(null)
  const [cue, setCue] = useState<TransitionCue | null>(null)
  const [frame, setFrame] = useState<VideoFrameRect | null>(null)

  const { cutPointsS } = project.preview
  const { transitionType, crossfadeS } = project.renderSettings
  const enabled = active && transitionsEnabled(project.renderSettings)

  useEffect(() => {
    if (!enabled || editTimeS === null) {
      setCue(null)
      return
    }

    const freezeCut = pendingFreezeCut(cutPointsS, editTimeS)
    if (freezeCut !== null && capturedCutRef.current !== freezeCut) {
      const video = videoRef.current
      const canvas = canvasRef.current
      if (video && canvas && video.videoWidth > 0) {
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        // Solo se dibuja para mostrarlo. El video llega del servidor local de
        // medios, así que el canvas queda «tainted» y no se pueden leer sus
        // píxeles de vuelta; pintarlo en pantalla sí está permitido.
        canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
        capturedCutRef.current = freezeCut
      }
    }

    setCue(transitionCueAt(cutPointsS, editTimeS, crossfadeS))
  }, [enabled, editTimeS, cutPointsS, crossfadeS, videoRef])

  // Cambiar de estilo o de duración invalida la captura pendiente: el corte que
  // se iba a animar puede haber dejado de tener transición.
  useEffect(() => {
    capturedCutRef.current = null
  }, [transitionType, crossfadeS, enabled])

  // El rectángulo visible depende del tamaño del panel y de la proporción del
  // material, así que hay que volver a medirlo cuando cambia cualquiera de los
  // dos. `loadedmetadata` cubre el segundo caso: antes de ese evento el
  // elemento todavía no conoce `videoWidth`.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const measure = (): void => {
      const box = video.getBoundingClientRect()
      setFrame(videoFrameRect(box.width, box.height, video.videoWidth, video.videoHeight))
    }

    measure()
    const resizes = new ResizeObserver(measure)
    resizes.observe(video)
    video.addEventListener('loadedmetadata', measure)

    return () => {
      resizes.disconnect()
      video.removeEventListener('loadedmetadata', measure)
    }
  }, [videoRef, project.mediaUrl])

  const visual = cue ? transitionVisual(transitionType, cue.progress, frame) : null

  return { canvasRef, cue, frame, visual }
}
