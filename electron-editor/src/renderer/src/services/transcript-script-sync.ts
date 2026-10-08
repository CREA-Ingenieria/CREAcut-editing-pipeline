import type { EditSegment, ProjectView, TranscriptSegment } from '../../../shared/contracts'

/** Finds the Whisper segment that owns the current source-video time. */
export function transcriptIndexAtTime(
  segments: TranscriptSegment[],
  timeS: number
): number | null {
  const index = segments.findIndex(
    (segment, position) =>
      segment.start <= timeS &&
      (timeS < segment.end ||
        (position === segments.length - 1 && timeS === segment.end))
  )
  return index >= 0 ? index : null
}

/**
 * Resolves a transcript item to its script sentence.
 *
 * The selected take is authoritative. Alternatives are only inspected when
 * the selected take has no relation with the requested transcript item. This
 * keeps the visual synchronization consistent with the user's current edit.
 */
export function scriptSegmentForTranscript(
  project: ProjectView,
  transcriptIndex: number | null
): EditSegment | null {
  if (transcriptIndex === null) return null

  for (const selectedOnly of [true, false]) {
    for (const segment of project.project.segments) {
      const candidates = selectedOnly
        ? segment.candidates.filter(
            (candidate) => candidate.id === segment.selected_candidate_id
          )
        : segment.candidates

      if (
        candidates.some(
          (candidate) =>
            candidate.segment_start_idx !== null &&
            candidate.segment_start_idx !== undefined &&
            candidate.segment_end_idx !== null &&
            candidate.segment_end_idx !== undefined &&
            candidate.segment_start_idx <= transcriptIndex &&
            transcriptIndex <= candidate.segment_end_idx
        )
      ) {
        return segment
      }
    }
  }

  return null
}
