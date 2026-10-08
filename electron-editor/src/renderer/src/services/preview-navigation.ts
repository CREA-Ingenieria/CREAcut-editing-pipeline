import type { PreviewClip, ProjectView } from '../../../shared/contracts'

const SEEK_EPSILON_S = 0.04

export type EditedPlaybackAction =
  | { kind: 'continue' }
  | { kind: 'seek'; sourceTimeS: number }
  | { kind: 'stop' }

function clipsInEditOrder(clips: PreviewClip[]): PreviewClip[] {
  return [...clips].sort((left, right) => left.editStartS - right.editStartS)
}

export function sourceToEditTime(project: ProjectView, sourceTimeS: number): number | null {
  const clip = project.preview.clips.find(
    (item, index) =>
      item.sourceStartS <= sourceTimeS &&
      (sourceTimeS < item.sourceEndS ||
        (index === project.preview.clips.length - 1 && sourceTimeS === item.sourceEndS))
  )
  return clip ? clip.editStartS + (sourceTimeS - clip.sourceStartS) : null
}

/**
 * Inverso de sourceToEditTime. Los limites internos son continuos por la
 * derecha (en un corte exacto gana el clip entrante) y solo el final de la
 * edicion mapea al fin del ultimo clip, igual que PreviewTimeline en Python.
 */
export function editToSourceTime(project: ProjectView, editTimeS: number): number | null {
  const clips = clipsInEditOrder(project.preview.clips)
  const clip = clips.find(
    (item, index) =>
      item.editStartS <= editTimeS &&
      (editTimeS < item.editEndS || (index === clips.length - 1 && editTimeS === item.editEndS))
  )
  return clip ? clip.sourceStartS + (editTimeS - clip.editStartS) : null
}

export function nearestEditedSource(project: ProjectView, sourceTimeS: number): number | null {
  const clips = clipsInEditOrder(project.preview.clips)
  if (clips.length === 0) return null
  const current = clips.find(
    (clip) => clip.sourceStartS <= sourceTimeS && sourceTimeS < clip.sourceEndS
  )
  if (current) return Math.max(current.sourceStartS, Math.min(sourceTimeS, current.sourceEndS))
  return clips.find((clip) => clip.sourceStartS > sourceTimeS)?.sourceStartS
    ?? clips.at(-1)?.sourceStartS
    ?? null
}

/** Decides how edited playback crosses discarded gaps in the source video. */
export function editedPlaybackAction(
  project: ProjectView,
  sourceTimeS: number
): EditedPlaybackAction {
  const current = project.preview.clips.find(
    (clip) =>
      clip.sourceStartS - 0.03 <= sourceTimeS &&
      sourceTimeS < clip.sourceEndS - 0.035
  )
  if (current) return { kind: 'continue' }

  const next = clipsInEditOrder(project.preview.clips).find(
    (clip) => clip.sourceStartS > sourceTimeS + 0.02
  )
  return next
    ? { kind: 'seek', sourceTimeS: next.sourceStartS }
    : { kind: 'stop' }
}

/**
 * Navigates complete edited playback blocks, not the individual script
 * segments contained inside them. The returned value is always the exact
 * source start of a preview clip and never a relative skip.
 */
export function adjacentEditedClipStart(
  project: ProjectView,
  sourceTimeS: number,
  direction: -1 | 1
): number | null {
  const ordered = clipsInEditOrder(project.preview.clips)
  if (ordered.length === 0) return null

  let currentIndex = ordered.findIndex(
    (clip, index) =>
      clip.sourceStartS <= sourceTimeS &&
      (sourceTimeS < clip.sourceEndS || (index === ordered.length - 1 && sourceTimeS === clip.sourceEndS))
  )
  // At a shared boundary the incoming clip owns the position. Only tolerate
  // a seek landing just before a start when no clip actually contains it.
  if (currentIndex < 0) {
    currentIndex = ordered.findIndex((clip) =>
      Math.abs(clip.sourceStartS - sourceTimeS) <= SEEK_EPSILON_S
    )
  }

  if (direction > 0) {
    if (currentIndex >= 0) return ordered[currentIndex + 1]?.sourceStartS ?? null
    return ordered.find(
      (clip) => clip.sourceStartS > sourceTimeS + SEEK_EPSILON_S
    )?.sourceStartS ?? null
  }

  if (currentIndex >= 0) {
    return ordered[currentIndex - 1]?.sourceStartS ?? null
  }
  return [...ordered]
    .reverse()
    .find(
      (clip) => clip.sourceStartS < sourceTimeS - SEEK_EPSILON_S
    )?.sourceStartS ?? null
}
