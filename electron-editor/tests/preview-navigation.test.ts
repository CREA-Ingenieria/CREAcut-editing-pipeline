import { describe, expect, it } from 'vitest'
import type { EditSegment, ProjectView } from '../src/shared/contracts'
import {
  adjacentEditedClipStart,
  editedPlaybackAction,
  nearestEditedSource,
  sourceToEditTime
} from '../src/renderer/src/services/preview-navigation'

function segment(id: string, start: number | null, end: number | null): EditSegment {
  return {
    id,
    paragraph_idx: 0,
    sentence_idx: 0,
    script_text: id,
    candidates: [],
    selected_candidate_id: start === null ? null : `candidate-${id}`,
    source_start_s: start,
    source_end_s: end,
    automatic_selection: { recommended_candidate_id: null, selection_reason: 'test' }
  }
}

function projectView(): ProjectView {
  return {
    project: {
      segments: [
        segment('primera', 5, 8),
        segment('sin-toma', null, null),
        segment('segunda', 15, 18),
        segment('tercera', 30, 34)
      ]
    },
    preview: {
      durationS: 10,
      clips: [
        { index: 0, sourceStartS: 5, sourceEndS: 8, editStartS: 0, editEndS: 3 },
        { index: 1, sourceStartS: 15, sourceEndS: 18, editStartS: 3, editEndS: 6 },
        { index: 2, sourceStartS: 30, sourceEndS: 34, editStartS: 6, editEndS: 10 }
      ],
      cutPointsS: [3, 6]
    }
  } as ProjectView
}

describe('navegación de propuestas', () => {
  it('siguiente avanza al próximo bloque editado y nunca al final del video', () => {
    const project = projectView()

    expect(adjacentEditedClipStart(project, 0, 1)).toBe(5)
    expect(adjacentEditedClipStart(project, 6, 1)).toBe(15)
    expect(adjacentEditedClipStart(project, 16, 1)).toBe(30)
    expect(adjacentEditedClipStart(project, 31, 1)).toBeNull()
  })

  it('anterior retrocede directamente al bloque anterior', () => {
    const project = projectView()

    expect(adjacentEditedClipStart(project, 16, -1)).toBe(5)
    expect(adjacentEditedClipStart(project, 15, -1)).toBe(5)
    expect(adjacentEditedClipStart(project, 4, -1)).toBeNull()
  })

  it('convierte correctamente el tiempo fuente de los clips editados', () => {
    const project = projectView()

    expect(sourceToEditTime(project, 16.5)).toBe(4.5)
    expect(sourceToEditTime(project, 12)).toBeNull()
    expect(nearestEditedSource(project, 12)).toBe(15)
    expect(nearestEditedSource(project, 99)).toBe(30)
  })

  it('tolera proyectos sin propuestas', () => {
    const project = projectView()
    project.project.segments = [segment('vacía', null, null)]
    project.preview.clips = []

    expect(adjacentEditedClipStart(project, 0, 1)).toBeNull()
    expect(adjacentEditedClipStart(project, 0, -1)).toBeNull()
    expect(nearestEditedSource(project, 0)).toBeNull()
  })

  it('ignora tomas internas y salta al inicio del siguiente bloque editado', () => {
    const project = projectView()
    project.project.segments.splice(1, 0, segment('toma-interna', 7, 7.8))

    expect(adjacentEditedClipStart(project, 6, 1)).toBe(15)
  })

  it('mantiene la reproducción dentro de una toma editada', () => {
    expect(editedPlaybackAction(projectView(), 6)).toEqual({ kind: 'continue' })
  })

  it('salta los descartes hacia la siguiente toma editada', () => {
    expect(editedPlaybackAction(projectView(), 10)).toEqual({
      kind: 'seek',
      sourceTimeS: 15
    })
  })

  it('detiene la reproducción después de la última toma', () => {
    expect(editedPlaybackAction(projectView(), 34)).toEqual({ kind: 'stop' })
  })
})
