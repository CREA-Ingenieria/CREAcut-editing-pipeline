import { useEffect, useMemo, useRef, useState } from 'react'
import type { SlidePage, TimelineMedia, TimelineRegion, VisualEffectRange } from '../../shared/contracts'
import { visualEffectLabel } from './services/visual-effects'
import { trimSlidesAroundSelection } from './services/slide-timing'
import type { ThemeMode } from './types/editor'
import { formatTime } from './format'

interface TimelineProps {
  durationS: number
  regions: TimelineRegion[]
  playheadS: number
  followPlayhead?: boolean
  selectedRegionId: string | null
  media: TimelineMedia | null
  pixelsPerSecond: number
  theme: ThemeMode
  /** Sin edicion: ni arrastre de limites ni seleccion de region, solo seek. */
  readOnly?: boolean
  label?: string
  onSeek: (timeS: number) => void
  onSelectRegion: (regionId: string) => void
  onMoveBoundary: (oldTimeS: number, newTimeS: number) => void
  effectRanges?: VisualEffectRange[]
  selectedEffectId?: string | null
  onSelectEffect?: (effectId: string) => void
  onUpdateEffectRange?: (effectId: string, startS: number, endS: number) => void
  slidePages?: SlidePage[]
  selectedSlideId?: string | null
  onSelectSlide?: (slideId: string) => void
  onUpdateSlideTiming?: (slideId: string, startS: number, endS: number) => void
}

// Paletas del canvas: el <canvas> dibuja de forma imperativa y no puede leer
// las custom properties CSS, asi que el tema se resuelve aqui explicitamente.
// Conservado usa el cian de marca y descartado el morado; el tono cambia por
// tema para mantener el contraste sobre cada fondo, no el significado.
export const TIMELINE_PALETTES: Record<
  ThemeMode,
  {
    canvasBg: string
    trackBg: string
    gridLine: string
    gridLineMinor: string
    rulerText: string
    rulerBorder: string
    thumbBg: string
    thumbText: string
    waveformBg: string
    waveformLine: string
    keepFill: string
    discardFill: string
    discardHatch: string
    regionBorder: string
    keepBorder: string
    selectionRing: string
    hoverRing: string
    playheadHalo: string | null
    dragBoundary: string
    effectFill: string
    effectSelected: string
    slideFill: string
    slideSelected: string
    slideDisabledBorder: string
  }
> = {
  dark: {
    canvasBg: '#0c1017',
    trackBg: '#12171f',
    gridLine: '#2b3341',
    gridLineMinor: '#1c222c',
    rulerText: '#8e99ab',
    rulerBorder: '#39424f',
    thumbBg: '#161c27',
    thumbText: '#5f6b7c',
    waveformBg: '#111823',
    waveformLine: '#5d8daf',
    keepFill: '#00A9CE',
    discardFill: '#8B2BC4',
    // sobre fondo oscuro la trama tiene que aclarar, no oscurecer: la version
    // oscura hundia el morado a ~1.5:1 y el bloque se leia como negro.
    discardHatch: 'rgba(255, 255, 255, 0.16)',
    regionBorder: '#11151d',
    keepBorder: '#e8fff6',
    selectionRing: '#F5E600',
    hoverRing: 'rgba(255, 255, 255, 0.55)',
    playheadHalo: null,
    dragBoundary: '#ffffff',
    effectFill: '#C8238D',
    effectSelected: '#F5E600',
    slideFill: '#E07B39',
    slideSelected: '#F5E600',
    slideDisabledBorder: '#8e99ab'
  },
  light: {
    canvasBg: '#eef2f6',
    trackBg: '#f8fafc',
    gridLine: '#c6cfda',
    gridLineMinor: '#dde4eb',
    rulerText: '#5a6472',
    rulerBorder: '#b6c0cc',
    thumbBg: '#e5eaf0',
    thumbText: '#5a6472',
    waveformBg: '#e5eaf0',
    waveformLine: '#3f6f86',
    keepFill: '#00819E',
    discardFill: '#8B1967',
    discardHatch: 'rgba(6, 8, 12, 0.45)',
    regionBorder: '#f8fafc',
    keepBorder: '#0f172a',
    selectionRing: '#0f172a',
    hoverRing: 'rgba(15, 23, 42, 0.45)',
    // el amarillo de marca (#F5E600) es muy claro para leerse solo sobre un
    // canvas casi blanco: en claro se le agrega un halo oscuro por debajo.
    playheadHalo: '#0f172a',
    dragBoundary: '#0f172a',
    effectFill: '#8B1967',
    effectSelected: '#00A9CE',
    slideFill: '#B25716',
    slideSelected: '#00A9CE',
    slideDisabledBorder: '#5a6472'
  }
}

// Amarillo de marca del playhead. Es el unico color de la paleta que no
// compite ni con el cian conservado ni con el morado descartado, asi que la
// cabeza de reproduccion se lee sobre cualquiera de los dos.
const BRAND_YELLOW = '#F5E600'

export type TimelineTrackKey = 'video' | 'audio' | 'effects' | 'regions' | 'slides'

export interface TimelineTrack {
  key: TimelineTrackKey
  label: string
  top: number
  height: number
}

export const TIMELINE_RULER_HEIGHT = 26

/**
 * Alto reservado para la barra de desplazamiento horizontal del lienzo.
 *
 * La barra se dibuja **dentro** del contenedor, así que sin este margen se
 * come los últimos píxeles de la última pista: la fila de diapositivas
 * aparecía cortada por abajo aunque el contenedor midiera exactamente lo que
 * mide el lienzo.
 */
export const TIMELINE_SCROLLBAR_HEIGHT = 10

/**
 * Geometría de las pistas, en un único sitio.
 *
 * El `<canvas>` dibuja con estos números y la columna de nombres se coloca con
 * los mismos, así que no pueden desincronizarse. La versión anterior tenía las
 * constantes repartidas entre el componente y una altura fija en `styles.css`:
 * al añadir la pista de diapositivas, el contenedor siguió midiendo lo de
 * antes y recortó la fila nueva por abajo. Aquí la altura del contenedor sale
 * de esta misma función.
 *
 * La pista de diapositivas solo existe cuando hay diapositivas importadas: una
 * fila vacía permanente son 24px de ruido en la pista más densa del editor.
 */
export function timelineTracks(hasSlides: boolean): TimelineTrack[] {
  const tracks: TimelineTrack[] = [
    { key: 'video', label: 'Video', top: TIMELINE_RULER_HEIGHT + 2, height: 54 },
    { key: 'audio', label: 'Audio', top: TIMELINE_RULER_HEIGHT + 58, height: 36 },
    { key: 'effects', label: 'Efectos', top: TIMELINE_RULER_HEIGHT + 96, height: 22 },
    { key: 'regions', label: 'Cortes', top: TIMELINE_RULER_HEIGHT + 120, height: 40 }
  ]
  if (hasSlides) {
    tracks.push({ key: 'slides', label: 'Diapositivas', top: TIMELINE_RULER_HEIGHT + 162, height: 22 })
  }
  return tracks
}

export function timelineHeight(tracks: TimelineTrack[]): number {
  const last = tracks[tracks.length - 1]
  return last ? last.top + last.height + 2 : TIMELINE_RULER_HEIGHT + 2
}

function trackAt(tracks: TimelineTrack[], key: TimelineTrackKey): TimelineTrack | null {
  return tracks.find((item) => item.key === key) ?? null
}

/** Marcas principales cada ~90px y una subdivisión intermedia. */
function tickStep(pixelsPerSecond: number): number {
  const candidates = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
  return candidates.find((step) => step * pixelsPerSecond >= 90) ?? 600
}

type HoverTarget = { kind: 'effect' | 'slide' | 'region'; id: string } | null

export function Timeline({
  durationS,
  regions,
  playheadS,
  followPlayhead = false,
  selectedRegionId,
  media,
  pixelsPerSecond,
  theme,
  readOnly = false,
  label = 'Línea de tiempo del video fuente',
  onSeek,
  onSelectRegion,
  onMoveBoundary,
  effectRanges = [],
  selectedEffectId = null,
  onSelectEffect,
  onUpdateEffectRange,
  slidePages = [],
  selectedSlideId = null,
  onSelectSlide,
  onUpdateSlideTiming
}: TimelineProps): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [viewportWidth, setViewportWidth] = useState(900)
  const [images, setImages] = useState<HTMLImageElement[]>([])
  const [hover, setHover] = useState<HoverTarget>(null)
  const [dragBoundary, setDragBoundary] = useState<{ oldTimeS: number; newTimeS: number } | null>(null)
  const [dragEffect, setDragEffect] = useState<{
    id: string
    mode: 'move' | 'start' | 'end'
    anchorS: number
    originalStartS: number
    originalEndS: number
    startS: number
    endS: number
  } | null>(null)
  const [dragSlide, setDragSlide] = useState<{
    id: string
    mode: 'move' | 'start' | 'end'
    anchorS: number
    originalStartS: number
    originalEndS: number
    startS: number
    endS: number
  } | null>(null)
  const width = Math.max(viewportWidth - 2, Math.ceil(durationS * pixelsPerSecond))
  const palette = TIMELINE_PALETTES[theme]
  const tracks = useMemo(() => timelineTracks(slidePages.length > 0), [slidePages.length])
  const height = timelineHeight(tracks)
  const videoTrack = trackAt(tracks, 'video')
  const audioTrack = trackAt(tracks, 'audio')
  const effectTrack = trackAt(tracks, 'effects')
  const regionTrack = trackAt(tracks, 'regions')
  const slideTrack = trackAt(tracks, 'slides')

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver(([entry]) => setViewportWidth(entry.contentRect.width))
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!followPlayhead || dragSlide || dragEffect || dragBoundary || !container || durationS <= 0 || !Number.isFinite(playheadS)) return

    const playheadX = (Math.min(durationS, Math.max(0, playheadS)) / durationS) * width
    const safeMargin = Math.min(72, container.clientWidth * 0.15)
    const visibleStart = container.scrollLeft + safeMargin
    const visibleEnd = container.scrollLeft + container.clientWidth - safeMargin

    if (playheadX < visibleStart || playheadX > visibleEnd) {
      const maximumScroll = Math.max(0, container.scrollWidth - container.clientWidth)
      container.scrollTo({
        left: Math.min(maximumScroll, Math.max(0, playheadX - container.clientWidth / 2)),
        behavior: 'auto'
      })
    }
  }, [durationS, playheadS, width, followPlayhead, dragSlide, dragEffect, dragBoundary])

  useEffect(() => {
    let cancelled = false
    if (!media?.thumbnails.length) {
      setImages([])
      return
    }
    Promise.all(
      media.thumbnails.map(
        (item) =>
          new Promise<HTMLImageElement>((resolve) => {
            const image = new Image()
            image.onload = () => resolve(image)
            image.onerror = () => resolve(image)
            image.src = item.url
          })
      )
    ).then((loaded) => {
      if (!cancelled) setImages(loaded)
    })
    return () => {
      cancelled = true
    }
  }, [media])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ratio = window.devicePixelRatio || 1
    canvas.width = Math.round(width * ratio)
    canvas.height = Math.round(height * ratio)
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    const context = canvas.getContext('2d')
    if (!context) return
    context.setTransform(ratio, 0, 0, ratio, 0, 0)

    const xAt = (timeS: number): number => (timeS / durationS) * width
    context.clearRect(0, 0, width, height)
    context.fillStyle = palette.canvasBg
    context.fillRect(0, 0, width, height)

    // Fondo propio de cada pista: sin él las filas se leen como una sola
    // superficie y hay que contar píxeles para saber dónde acaba cada una.
    for (const track of tracks) {
      context.fillStyle = palette.trackBg
      context.fillRect(0, track.top, width, track.height)
    }

    // --- Regla -------------------------------------------------------------
    const step = tickStep(width / durationS)
    const bodyTop = TIMELINE_RULER_HEIGHT
    context.font = '10px Inter Variable, sans-serif'
    context.textBaseline = 'top'
    for (let time = 0; time <= durationS + 0.0001; time += step / 2) {
      const x = xAt(time)
      // Las marcas intermedias no llevan cifra y su línea es más tenue: dan
      // escala sin convertir la pista en una rejilla de cuaderno.
      const major = Math.abs(time / step - Math.round(time / step)) < 0.001
      context.strokeStyle = major ? palette.gridLine : palette.gridLineMinor
      context.beginPath()
      context.moveTo(x + 0.5, major ? 14 : 19)
      context.lineTo(x + 0.5, major ? height : bodyTop)
      context.stroke()
      if (major) {
        context.fillStyle = palette.rulerText
        context.fillText(formatTime(time), x + 5, 4)
      }
    }
    context.strokeStyle = palette.rulerBorder
    context.beginPath()
    context.moveTo(0, bodyTop + 0.5)
    context.lineTo(width, bodyTop + 0.5)
    context.stroke()

    // --- Pista de video ----------------------------------------------------
    if (videoTrack) {
      if (media?.thumbnails.length && images.length === media.thumbnails.length) {
        const slotWidth = Math.max(90, width / media.thumbnails.length)
        media.thumbnails.forEach((thumbnail, index) => {
          const image = images[index]
          if (!image?.naturalWidth) return
          const centerX = xAt(thumbnail.timeS)
          const drawWidth = Math.min(160, slotWidth)
          const left = Math.max(0, Math.min(width - drawWidth, centerX - drawWidth / 2))
          context.save()
          context.beginPath()
          context.rect(left, videoTrack.top, drawWidth - 2, videoTrack.height)
          context.clip()
          const scale = Math.max(drawWidth / image.naturalWidth, videoTrack.height / image.naturalHeight)
          const scaledWidth = image.naturalWidth * scale
          const scaledHeight = image.naturalHeight * scale
          context.globalAlpha = 0.78
          context.drawImage(
            image,
            left + (drawWidth - scaledWidth) / 2,
            videoTrack.top + (videoTrack.height - scaledHeight) / 2,
            scaledWidth,
            scaledHeight
          )
          context.restore()
        })
        context.globalAlpha = 1
      } else {
        context.fillStyle = palette.thumbBg
        context.fillRect(0, videoTrack.top, width, videoTrack.height)
        context.fillStyle = palette.thumbText
        context.font = '10px Inter Variable, sans-serif'
        context.fillText('Preparando miniaturas…', 10, videoTrack.top + videoTrack.height / 2 - 5)
      }
    }

    // --- Pista de audio ----------------------------------------------------
    const waveform = media?.waveform ?? []
    if (audioTrack) {
      context.fillStyle = palette.waveformBg
      context.fillRect(0, audioTrack.top, width, audioTrack.height)
      if (waveform.length) {
        context.strokeStyle = palette.waveformLine
        context.lineWidth = 1
        const middle = audioTrack.top + audioTrack.height / 2
        const barWidth = width / waveform.length
        waveform.forEach((peak, index) => {
          const x = index * barWidth
          const amplitude = Math.max(1, peak * (audioTrack.height / 2 - 2))
          context.beginPath()
          context.moveTo(x, middle - amplitude)
          context.lineTo(x, middle + amplitude)
          context.stroke()
        })
      }
    }

    // --- Pista de efectos --------------------------------------------------
    if (effectTrack) {
      const displayedEffects = effectRanges.map((item) =>
        dragEffect?.id === item.id
          ? { ...item, startS: dragEffect.startS, endS: dragEffect.endS }
          : item
      )
      for (const effect of displayedEffects) {
        const startX = xAt(effect.startS)
        const endX = xAt(effect.endS)
        const selected = effect.id === selectedEffectId
        const hovered = hover?.kind === 'effect' && hover.id === effect.id
        context.fillStyle = palette.effectFill
        context.globalAlpha = selected ? 1 : hovered ? 0.9 : 0.72
        context.fillRect(startX, effectTrack.top + 1, Math.max(2, endX - startX), effectTrack.height - 2)
        context.globalAlpha = 1
        context.strokeStyle = selected
          ? palette.selectionRing
          : hovered
            ? palette.hoverRing
            : palette.keepBorder
        context.lineWidth = selected ? 2 : 1
        context.strokeRect(startX + 0.5, effectTrack.top + 1.5, Math.max(1, endX - startX - 1), effectTrack.height - 3)
        context.fillStyle = '#ffffff'
        context.font = '9px Inter Variable, sans-serif'
        context.fillText(
          visualEffectLabel(effect.kind),
          startX + 6,
          effectTrack.top + effectTrack.height / 2 - 4,
          Math.max(0, endX - startX - 12)
        )
        // Asideros de los extremos: marcan dónde se agarra para redimensionar.
        context.fillStyle = selected ? palette.selectionRing : palette.keepBorder
        context.fillRect(startX, effectTrack.top + 1, 2, effectTrack.height - 2)
        context.fillRect(endX - 2, effectTrack.top + 1, 2, effectTrack.height - 2)
      }
    }

    // --- Pista de cortes ---------------------------------------------------
    if (regionTrack) {
      for (const region of regions) {
        const startX = xAt(region.startS)
        const endX = xAt(region.endS)
        const selected = region.id === selectedRegionId
        const hovered = hover?.kind === 'region' && hover.id === region.id
        context.fillStyle = region.keep ? palette.keepFill : palette.discardFill
        context.globalAlpha = selected ? 1 : hovered ? 0.94 : 0.85
        context.fillRect(startX, regionTrack.top, Math.max(1, endX - startX), regionTrack.height)
        context.globalAlpha = 1
        if (!region.keep) {
          // La trama arranca antes de startX para que la diagonal entre por el
          // borde, asi que hay que recortarla a la region: sin el clip pinta
          // rayas sobre la region vecina.
          context.save()
          context.beginPath()
          context.rect(startX, regionTrack.top, Math.max(1, endX - startX), regionTrack.height)
          context.clip()
          context.fillStyle = palette.discardHatch
          for (let x = startX - regionTrack.height; x < endX; x += 12) {
            context.beginPath()
            context.moveTo(x, regionTrack.top + regionTrack.height)
            context.lineTo(x + regionTrack.height, regionTrack.top)
            context.lineTo(x + regionTrack.height + 5, regionTrack.top)
            context.lineTo(x + 5, regionTrack.top + regionTrack.height)
            context.closePath()
            context.fill()
          }
          context.restore()
        }
        // La selección se dibuja: sin ella, elegir un corte en la línea de
        // tiempo activaba los botones del panel sin ninguna señal de cuál
        // estaba en juego, y la selección quedaba desincronizada con la vista.
        context.strokeStyle = selected
          ? palette.selectionRing
          : hovered
            ? palette.hoverRing
            : region.keep
              ? palette.keepBorder
              : palette.regionBorder
        context.lineWidth = selected ? 2 : region.keep ? 1.5 : 1
        const inset = selected ? 1 : 0.5
        context.strokeRect(
          startX + inset,
          regionTrack.top + inset,
          Math.max(1, endX - startX - inset * 2),
          regionTrack.height - inset * 2
        )
      }
    }

    // --- Pista de diapositivas ---------------------------------------------
    if (slideTrack && slidePages.length) {
      const adjustedSlides = dragSlide
        ? trimSlidesAroundSelection(slidePages, dragSlide.id, dragSlide.startS, dragSlide.endS)
        : slidePages
      const displayedSlides = adjustedSlides.filter(
        (page): page is SlidePage & { startS: number; endS: number } =>
          page.startS !== null && page.endS !== null
      )
      for (const page of displayedSlides) {
        const startX = xAt(page.startS)
        const endX = xAt(page.endS)
        const selected = page.id === selectedSlideId
        const hovered = hover?.kind === 'slide' && hover.id === page.id
        context.fillStyle = palette.slideFill
        context.globalAlpha = selected ? 1 : page.enabled ? (hovered ? 0.92 : 0.78) : 0.4
        context.fillRect(startX, slideTrack.top + 1, Math.max(2, endX - startX), slideTrack.height - 2)
        context.globalAlpha = 1
        context.strokeStyle = selected
          ? palette.selectionRing
          : hovered
            ? palette.hoverRing
            : page.enabled
              ? palette.keepBorder
              : palette.slideDisabledBorder
        context.lineWidth = selected ? 2 : 1
        if (!page.enabled) context.setLineDash([3, 3])
        context.strokeRect(startX + 0.5, slideTrack.top + 1.5, Math.max(1, endX - startX - 1), slideTrack.height - 3)
        context.setLineDash([])
        context.fillStyle = '#ffffff'
        context.font = '9px Inter Variable, sans-serif'
        context.fillText(
          `#${page.index + 1}`,
          startX + 6,
          slideTrack.top + slideTrack.height / 2 - 4,
          Math.max(0, endX - startX - 12)
        )
        context.fillStyle = selected ? palette.selectionRing : page.enabled ? palette.keepBorder : palette.slideDisabledBorder
        context.fillRect(startX, slideTrack.top + 1, 2, slideTrack.height - 2)
        context.fillRect(endX - 2, slideTrack.top + 1, 2, slideTrack.height - 2)
      }
    }

    // --- Cabezal de reproducción -------------------------------------------
    const playheadX = xAt(Math.min(durationS, Math.max(0, playheadS)))
    if (palette.playheadHalo) {
      context.strokeStyle = palette.playheadHalo
      context.lineWidth = 4
      context.beginPath()
      context.moveTo(playheadX, 0)
      context.lineTo(playheadX, height)
      context.stroke()
    }
    context.strokeStyle = BRAND_YELLOW
    context.lineWidth = 2
    context.beginPath()
    context.moveTo(playheadX, 0)
    context.lineTo(playheadX, height)
    context.stroke()
    context.fillStyle = BRAND_YELLOW
    context.beginPath()
    context.moveTo(playheadX - 6, 0)
    context.lineTo(playheadX + 6, 0)
    context.lineTo(playheadX, 9)
    context.closePath()
    context.fill()
    if (palette.playheadHalo) {
      context.strokeStyle = palette.playheadHalo
      context.lineWidth = 1
      context.beginPath()
      context.moveTo(playheadX - 6, 0)
      context.lineTo(playheadX + 6, 0)
      context.lineTo(playheadX, 9)
      context.closePath()
      context.stroke()
    }
    if (dragBoundary && regionTrack) {
      const dragX = xAt(dragBoundary.newTimeS)
      context.strokeStyle = palette.dragBoundary
      context.lineWidth = 2
      context.setLineDash([5, 4])
      context.beginPath()
      context.moveTo(dragX, regionTrack.top - 8)
      context.lineTo(dragX, height)
      context.stroke()
      context.setLineDash([])
    }
  }, [
    audioTrack,
    dragBoundary,
    dragEffect,
    dragSlide,
    durationS,
    effectRanges,
    effectTrack,
    height,
    hover,
    images,
    media,
    palette,
    playheadS,
    regionTrack,
    regions,
    selectedEffectId,
    selectedRegionId,
    selectedSlideId,
    slidePages,
    slideTrack,
    theme,
    tracks,
    videoTrack,
    width
  ])

  const timeAtPointer = (event: React.PointerEvent<HTMLCanvasElement>): number => {
    const bounds = event.currentTarget.getBoundingClientRect()
    return Math.min(durationS, Math.max(0, ((event.clientX - bounds.left) / bounds.width) * durationS))
  }

  const yAtPointer = (event: React.PointerEvent<HTMLCanvasElement>): number => {
    const bounds = event.currentTarget.getBoundingClientRect()
    return ((event.clientY - bounds.top) / bounds.height) * height
  }

  /**
   * Pista bajo el puntero.
   *
   * Se resuelve por cercanía y no con una banda de tolerancia por pista: las
   * filas están separadas por 2px, así que dos bandas de ±4px se solapaban y
   * el borde superior de CORTES quedaba dentro de la banda de EFECTOS — un
   * clic ahí no seleccionaba la región. Con la pista más cercana no hay ni
   * solapes ni zonas muertas.
   */
  const trackAtY = (y: number): TimelineTrackKey | null => {
    if (y < TIMELINE_RULER_HEIGHT) return null
    let closest: TimelineTrack | null = null
    let closestDistance = Number.POSITIVE_INFINITY
    for (const track of tracks) {
      const distance =
        y < track.top ? track.top - y : y > track.top + track.height ? y - (track.top + track.height) : 0
      if (distance < closestDistance) {
        closestDistance = distance
        closest = track
      }
    }
    return closest && closestDistance <= 6 ? closest.key : null
  }

  const isOnRegionTrack = (y: number): boolean =>
    Boolean(regionTrack && y >= regionTrack.top && y < regionTrack.top + regionTrack.height)

  /**
   * Cursor bajo el puntero. Se escribe directamente sobre el elemento y no por
   * estado de React: cambia en cada movimiento del ratón y un render por
   * fotograma sobre un canvas con miniaturas no sale gratis.
   */
  function updateCursor(canvas: HTMLCanvasElement, y: number, timeS: number, toleranceS: number): void {
    if (readOnly) {
      canvas.style.cursor = 'crosshair'
      return
    }
    const track = trackAtY(y)
    const nearEdge = (start: number, end: number): boolean =>
      Math.abs(timeS - start) <= toleranceS || Math.abs(timeS - end) <= toleranceS
    if (track === 'effects') {
      const effect = effectRanges.find((item) => item.startS - toleranceS <= timeS && timeS <= item.endS + toleranceS)
      canvas.style.cursor = effect ? (nearEdge(effect.startS, effect.endS) ? 'ew-resize' : 'grab') : 'crosshair'
      return
    }
    if (track === 'slides') {
      const page = slidePages.find(
        (item) => item.startS !== null && item.endS !== null && item.startS - toleranceS <= timeS && timeS <= item.endS + toleranceS
      )
      canvas.style.cursor = page ? (nearEdge(page.startS!, page.endS!) ? 'ew-resize' : 'grab') : 'crosshair'
      return
    }
    const boundary = isOnRegionTrack(y) &&
      regions.slice(1).some((region) => Math.abs(region.startS - timeS) <= toleranceS)
    canvas.style.cursor = boundary ? 'ew-resize' : 'crosshair'
  }

  /** Solo se guarda en estado cuando cambia de bloque: un redibujado por bloque, no por píxel. */
  function updateHover(y: number, timeS: number, toleranceS: number): void {
    const track = trackAtY(y)
    let next: HoverTarget = null
    if (track === 'effects') {
      const effect = effectRanges.find((item) => item.startS - toleranceS <= timeS && timeS <= item.endS + toleranceS)
      if (effect) next = { kind: 'effect', id: effect.id }
    } else if (track === 'slides') {
      const page = slidePages.find(
        (item) => item.startS !== null && item.endS !== null && item.startS - toleranceS <= timeS && timeS <= item.endS + toleranceS
      )
      if (page) next = { kind: 'slide', id: page.id }
    } else if (track === 'regions') {
      const region = regions.find((item) => item.startS <= timeS && timeS <= item.endS)
      if (region) next = { kind: 'region', id: region.id }
    }
    setHover((current) =>
      current?.kind === next?.kind && current?.id === next?.id ? current : next
    )
  }

  return (
    <div className="timeline-scroll" ref={containerRef} style={{ height: height + TIMELINE_SCROLLBAR_HEIGHT }}>
      <canvas
        ref={canvasRef}
        className="timeline-canvas"
        aria-label={label}
        onPointerDown={(event) => {
          const timeS = timeAtPointer(event)
          if (readOnly) {
            onSeek(timeS)
            return
          }
          const y = yAtPointer(event)
          const track = trackAtY(y)
          const toleranceS = (8 / width) * durationS
          if (track === 'effects') {
            const effect = [...effectRanges].reverse().find(
              (item) => item.startS - toleranceS <= timeS && timeS <= item.endS + toleranceS
            )
            if (effect) {
              const mode = Math.abs(timeS - effect.startS) <= toleranceS
                ? 'start'
                : Math.abs(timeS - effect.endS) <= toleranceS
                  ? 'end'
                  : 'move'
              event.currentTarget.setPointerCapture(event.pointerId)
              onSelectEffect?.(effect.id)
              setDragEffect({
                id: effect.id,
                mode,
                anchorS: timeS,
                originalStartS: effect.startS,
                originalEndS: effect.endS,
                startS: effect.startS,
                endS: effect.endS
              })
              return
            }
            onSeek(timeS)
            return
          }
          if (track === 'slides') {
            const placed = slidePages.filter((page) => page.startS !== null && page.endS !== null)
            const page = [...placed].sort((a, b) => Number(b.id === selectedSlideId) - Number(a.id === selectedSlideId)).find(
              (item) => item.startS! - toleranceS <= timeS && timeS <= item.endS! + toleranceS
            )
            if (page) {
              const mode = Math.abs(timeS - page.startS!) <= toleranceS
                ? 'start'
                : Math.abs(timeS - page.endS!) <= toleranceS
                  ? 'end'
                  : 'move'
              event.currentTarget.setPointerCapture(event.pointerId)
              onSelectSlide?.(page.id)
              setDragSlide({
                id: page.id,
                mode,
                anchorS: timeS,
                originalStartS: page.startS!,
                originalEndS: page.endS!,
                startS: page.startS!,
                endS: page.endS!
              })
              return
            }
            onSeek(timeS)
            return
          }
          if (!isOnRegionTrack(y)) {
            onSeek(timeS)
            return
          }
          const boundaries = regions.slice(1).map((region) => region.startS)
          const boundary = boundaries.find((value) => Math.abs(value - timeS) <= toleranceS)
          if (boundary !== undefined) {
            event.currentTarget.setPointerCapture(event.pointerId)
            setDragBoundary({ oldTimeS: boundary, newTimeS: boundary })
            return
          }
          const region = regions.find(
            (item, index) =>
              item.startS <= timeS &&
              (timeS < item.endS || (index === regions.length - 1 && timeS === item.endS))
          )
          if (region) onSelectRegion(region.id)
          onSeek(timeS)
        }}
        onPointerMove={(event) => {
          const timeS = timeAtPointer(event)
          if (dragEffect) {
            if (dragEffect.mode === 'start') {
              setDragEffect({ ...dragEffect, startS: Math.min(dragEffect.endS - 0.1, timeS) })
            } else if (dragEffect.mode === 'end') {
              setDragEffect({ ...dragEffect, endS: Math.max(dragEffect.startS + 0.1, timeS) })
            } else {
              const length = dragEffect.originalEndS - dragEffect.originalStartS
              const proposedStart = dragEffect.originalStartS + (timeS - dragEffect.anchorS)
              const startS = Math.min(durationS - length, Math.max(0, proposedStart))
              setDragEffect({ ...dragEffect, startS, endS: startS + length })
            }
            return
          }
          if (dragSlide) {
            // The active slide wins; neighbours are trimmed in the canvas
            // preview and atomically by the backend when the drag is saved.
            const lowerBound = 0
            const upperBound = durationS
            if (dragSlide.mode === 'start') {
              setDragSlide({ ...dragSlide, startS: Math.max(lowerBound, Math.min(dragSlide.endS - 0.1, timeS)) })
            } else if (dragSlide.mode === 'end') {
              setDragSlide({ ...dragSlide, endS: Math.min(upperBound, Math.max(dragSlide.startS + 0.1, timeS)) })
            } else {
              const length = dragSlide.originalEndS - dragSlide.originalStartS
              const proposedStart = dragSlide.originalStartS + (timeS - dragSlide.anchorS)
              const startS = Math.min(upperBound - length, Math.max(lowerBound, proposedStart))
              setDragSlide({ ...dragSlide, startS, endS: startS + length })
            }
            return
          }
          if (dragBoundary) {
            setDragBoundary({ ...dragBoundary, newTimeS: timeS })
            return
          }
          const y = yAtPointer(event)
          const toleranceS = (8 / width) * durationS
          updateCursor(event.currentTarget, y, timeS, toleranceS)
          updateHover(y, timeS, toleranceS)
        }}
        onPointerLeave={() => setHover(null)}
        onPointerUp={(event) => {
          if (dragEffect) {
            event.currentTarget.releasePointerCapture(event.pointerId)
            const completed = dragEffect
            setDragEffect(null)
            if (
              Math.abs(completed.startS - completed.originalStartS) > 0.001 ||
              Math.abs(completed.endS - completed.originalEndS) > 0.001
            ) {
              onUpdateEffectRange?.(completed.id, completed.startS, completed.endS)
            }
            return
          }
          if (dragSlide) {
            event.currentTarget.releasePointerCapture(event.pointerId)
            const completed = dragSlide
            setDragSlide(null)
            if (
              Math.abs(completed.startS - completed.originalStartS) > 0.001 ||
              Math.abs(completed.endS - completed.originalEndS) > 0.001
            ) {
              onUpdateSlideTiming?.(completed.id, completed.startS, completed.endS)
            }
            return
          }
          if (!dragBoundary) return
          event.currentTarget.releasePointerCapture(event.pointerId)
          const finalBoundary = { ...dragBoundary, newTimeS: timeAtPointer(event) }
          setDragBoundary(null)
          if (Math.abs(finalBoundary.newTimeS - finalBoundary.oldTimeS) > 0.001) {
            onMoveBoundary(finalBoundary.oldTimeS, finalBoundary.newTimeS)
          }
        }}
        onPointerCancel={() => {
          setDragEffect(null)
          setDragSlide(null)
          setDragBoundary(null)
        }}
      />
    </div>
  )
}
