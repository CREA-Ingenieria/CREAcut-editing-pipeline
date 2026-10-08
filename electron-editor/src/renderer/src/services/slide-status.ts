import type { SlidePage } from '../../../shared/contracts'

// A slide's lifecycle has no dedicated history field on the backend model
// (see creacut/slides.py:SlidePage) -- only recommended_*/start_s/end_s/
// enabled. This derives the five states the "Diapositivas" UI needs to show
// (spec: "Sin analizar / Propuesta / Activa / Modificada manualmente /
// Desactivada") purely from those fields. One case is genuinely ambiguous
// with the data available: a proposal that was accepted and later disabled
// without ever being edited looks identical to one that was never accepted
// (both end up enabled=false with startS/endS still equal to the
// recommendation). That case is classified as "proposed", the far more
// common path in practice.
export type SlideStatus = 'unanalyzed' | 'proposed' | 'active' | 'modified' | 'disabled'

export const SLIDE_STATUS_LABEL: Record<SlideStatus, string> = {
  unanalyzed: 'Sin analizar',
  proposed: 'Propuesta',
  active: 'Activa',
  modified: 'Modificada manualmente',
  disabled: 'Desactivada'
}

export function slideStatus(page: SlidePage): SlideStatus {
  const hasRecommendation = page.recommendedStartS !== null && page.recommendedEndS !== null
  const hasCue = page.startS !== null && page.endS !== null
  const matchesRecommendation =
    hasCue &&
    hasRecommendation &&
    page.startS === page.recommendedStartS &&
    page.endS === page.recommendedEndS

  if (page.enabled) {
    // A slide added straight to the timeline without ever running "Analizar
    // y proponer" has no recommendation to diverge from -- just active.
    return !hasRecommendation || matchesRecommendation ? 'active' : 'modified'
  }
  if (hasCue && !matchesRecommendation) return 'disabled'
  if (hasRecommendation) return 'proposed'
  return 'unanalyzed'
}

export function slideConfidenceLabel(page: SlidePage): string | null {
  if (page.recommendedStartS === null || page.recommendedEndS === null) return null
  const level = page.recommendationScore >= 0.35 ? 'alta' : page.recommendationScore >= 0.15 ? 'media' : 'baja'
  const kind = page.recommendationMode === 'ordered-fallback' ? 'distribución por orden' : 'coincidencia semántica'
  return `Confianza ${level} · ${kind}`
}
