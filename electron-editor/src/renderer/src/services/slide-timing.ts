import type { SlidePage } from '../../../shared/contracts'

/** Keep this preview in sync with update_slide_page in creacut/slides.py. */
export function trimSlidesAroundSelection(
  pages: SlidePage[], selectedId: string, startS: number, endS: number
): SlidePage[] {
  return pages.map((page) => {
    if (page.id === selectedId) return { ...page, startS, endS }
    if (page.startS === null || page.endS === null || page.endS <= startS || page.startS >= endS) return page
    const left = startS - page.startS
    const right = page.endS - endS
    // A page has one cue: if surrounded, retain its larger remaining side.
    if (Math.max(left, right) < 0.001) return { ...page, startS: null, endS: null, enabled: false }
    return left >= right ? { ...page, endS: startS } : { ...page, startS: endS }
  })
}
