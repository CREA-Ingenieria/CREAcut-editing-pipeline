import { useRef, useState } from 'react'
import type { ProjectView } from '../../../shared/contracts'
import {
  adjacentEditedClipStart,
  editToSourceTime,
  editedPlaybackAction,
  nearestEditedSource,
  sourceToEditTime
} from '../services/preview-navigation'
import { SeekCoordinator } from '../services/seek-coordinator'
import type { PreviewMode } from '../types/editor'

interface PreviewPlaybackOptions {
  project: ProjectView | null
  onError: (message: string) => void
  onSeekSource: (timeS: number) => void
}

export interface PreviewPlaybackController {
  videoRef: React.RefObject<HTMLVideoElement>
  previewMode: PreviewMode
  playing: boolean
  sourceTimeS: number
  editTimeS: number | null
  reset: () => void
  seekSource: (timeS: number) => void
  seekEdit: (editTimeS: number) => void
  seekToSelection: (timeS: number) => void
  seekFromTimeline: (timeS: number) => void
  changeMode: (mode: PreviewMode) => void
  togglePlayback: () => Promise<void>
  jump: (direction: -1 | 1) => void
  onLoadedMetadata: (video: HTMLVideoElement) => void
  onSeeked: (video: HTMLVideoElement) => void
  onPlaying: () => void
  onPause: () => void
  onTimeUpdate: (video: HTMLVideoElement) => void
  onError: (video: HTMLVideoElement) => void
}

function mediaPlaybackError(video: HTMLVideoElement): string {
  const code = video.error?.code
  const details: Record<number, string> = {
    1: 'la carga fue cancelada',
    2: 'falló la lectura del archivo',
    3: 'Chromium no pudo decodificar el video',
    4: 'el formato o codec no es compatible'
  }
  return `No se pudo reproducir el video: ${details[code ?? 0] ?? 'error multimedia desconocido'}${video.error?.message ? ` (${video.error.message})` : ''}.`
}

export function usePreviewPlayback({
  project,
  onError,
  onSeekSource
}: PreviewPlaybackOptions): PreviewPlaybackController {
  const videoRef = useRef<HTMLVideoElement>(null)
  const seekCoordinatorRef = useRef(new SeekCoordinator())
  const [previewMode, setPreviewMode] = useState<PreviewMode>('source')
  const [playing, setPlaying] = useState(false)
  const [sourceTimeS, setSourceTimeS] = useState(0)

  function seekSource(timeS: number): void {
    const duration = project?.timeline.durationS ?? 0
    const bounded = Math.min(duration, Math.max(0, timeS))
    const video = videoRef.current
    const coordinator = seekCoordinatorRef.current
    coordinator.request(bounded)
    if (video && video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      const target = coordinator.targetToApply(video.currentTime)
      if (target !== null) video.currentTime = target
    }
    setSourceTimeS(bounded)
    onSeekSource(bounded)
  }

  function reset(): void {
    const video = videoRef.current
    if (video) {
      video.pause()
      video.currentTime = 0
    }
    seekCoordinatorRef.current.clear()
    setPreviewMode('source')
    setSourceTimeS(0)
    setPlaying(false)
  }

  // 'edit' y 'preview' comparten reproduccion: ambos saltan lo descartado.
  // Lo que los distingue es la linea de tiempo que dibuja TimelinePanel.
  const playsEdited = previewMode !== 'source'

  function seekEdit(editTimeS: number): void {
    if (!project) return
    const sourceTimeS = editToSourceTime(project, editTimeS)
    if (sourceTimeS !== null) seekSource(sourceTimeS)
  }

  function seekFromTimeline(timeS: number): void {
    if (project && playsEdited && sourceToEditTime(project, timeS) === null) {
      setPreviewMode('source')
    }
    seekSource(timeS)
  }

  function seekToSelection(timeS: number): void {
    const video = videoRef.current
    if (video && !video.paused) video.pause()
    setPreviewMode('source')
    seekSource(timeS)
  }

  function changeMode(mode: PreviewMode): void {
    setPreviewMode(mode)
    if (mode !== 'source' && project && sourceToEditTime(project, sourceTimeS) === null) {
      const target = nearestEditedSource(project, sourceTimeS)
      if (target !== null) seekSource(target)
    }
  }

  async function togglePlayback(): Promise<void> {
    const video = videoRef.current
    if (!video || !project?.mediaUrl) return
    if (!video.paused) {
      video.pause()
      return
    }
    if (playsEdited && sourceToEditTime(project, video.currentTime) === null) {
      const target = nearestEditedSource(project, video.currentTime)
      if (target === null) {
        onError('La edición propuesta no contiene clips para reproducir.')
        return
      }
      seekSource(target)
    }
    try {
      await video.play()
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function jump(direction: -1 | 1): void {
    if (!project) return
    const target = adjacentEditedClipStart(project, sourceTimeS, direction)
    if (target !== null) seekSource(target)
  }

  function enforceEditedPlayback(video: HTMLVideoElement): void {
    if (!project || !playsEdited || video.paused) return
    const action = editedPlaybackAction(project, video.currentTime)
    if (action.kind === 'seek') seekSource(action.sourceTimeS)
    else if (action.kind === 'stop') {
      video.pause()
      setPlaying(false)
    }
  }

  return {
    videoRef,
    previewMode,
    playing,
    sourceTimeS,
    editTimeS: project ? sourceToEditTime(project, sourceTimeS) : null,
    reset,
    seekSource,
    seekEdit,
    seekToSelection,
    seekFromTimeline,
    changeMode,
    togglePlayback,
    jump,
    onLoadedMetadata: (video) => {
      const target = seekCoordinatorRef.current.targetToApply(video.currentTime)
      if (target !== null) video.currentTime = target
    },
    onSeeked: (video) => {
      const retryTarget = seekCoordinatorRef.current.retryAfterSeeked(video.currentTime)
      if (retryTarget !== null) {
        video.currentTime = retryTarget
        return
      }
      setSourceTimeS(video.currentTime)
    },
    onPlaying: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onTimeUpdate: (video) => {
      if (!seekCoordinatorRef.current.acceptTimeUpdate(video.currentTime)) return
      setSourceTimeS(video.currentTime)
      enforceEditedPlayback(video)
    },
    onError: (video) => {
      setPlaying(false)
      onError(mediaPlaybackError(video))
    }
  }
}
