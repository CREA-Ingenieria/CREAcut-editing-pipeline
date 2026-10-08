import type {
  ProjectView,
  TimelineMedia,
  TimelineRegion,
  TimelineThumbnail
} from '../../../shared/contracts'
import { editToSourceTime, sourceToEditTime } from './preview-navigation'

/**
 * Proyecta la edicion final sobre una linea de tiempo propia.
 *
 * El contrato ya expone lo necesario: cada PreviewClip trae sus limites en
 * tiempo editado ademas de los del video fuente, asi que la vista del
 * resultado se deriva en el renderer sin pedir nada nuevo al puente Python.
 * Todas las regiones resultantes son conservadas por construccion: en la
 * edicion final no existe lo descartado, solo el corte entre un clip y el
 * siguiente.
 */
export function editedRegions(project: ProjectView): TimelineRegion[] {
  return [...project.preview.clips]
    .sort((left, right) => left.editStartS - right.editStartS)
    .map((clip) => ({
      id: `preview-clip-${clip.index}`,
      startS: clip.editStartS,
      endS: clip.editEndS,
      automaticKeep: true,
      keep: true,
      origin: 'preview',
      linkedSegmentIds: []
    }))
}

/**
 * Reproyecta miniaturas y forma de onda del video fuente sobre el eje editado.
 *
 * Las miniaturas que caen dentro de un tramo descartado desaparecen, que es
 * justo lo que debe ver el usuario. La onda se remuestrea por indice a partir
 * de los mismos buckets del video fuente: es una aproximacion visual para que
 * la tira acompane al corte, no una señal recalculada.
 */
export function editedMedia(
  project: ProjectView,
  media: TimelineMedia | null
): TimelineMedia | null {
  if (!media) return null

  const thumbnails = media.thumbnails
    .map((thumbnail): TimelineThumbnail | null => {
      const editTimeS = sourceToEditTime(project, thumbnail.timeS)
      return editTimeS === null ? null : { ...thumbnail, timeS: editTimeS }
    })
    .filter((thumbnail): thumbnail is TimelineThumbnail => thumbnail !== null)

  const buckets = media.waveform.length
  const editDurationS = project.preview.durationS
  const sourceDurationS = project.timeline.durationS
  const waveform =
    buckets > 0 && editDurationS > 0 && sourceDurationS > 0
      ? Array.from({ length: buckets }, (_unused, index) => {
          const sourceTimeS = editToSourceTime(
            project,
            ((index + 0.5) / buckets) * editDurationS
          )
          if (sourceTimeS === null) return 0
          const sourceIndex = Math.min(
            buckets - 1,
            Math.max(0, Math.floor((sourceTimeS / sourceDurationS) * buckets))
          )
          return media.waveform[sourceIndex]
        })
      : media.waveform

  return { ...media, thumbnails, waveform }
}
