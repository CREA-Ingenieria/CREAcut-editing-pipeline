import type { VisualEffectKind, VisualEffectRange } from '../../../shared/contracts'

export const VISUAL_EFFECT_OPTIONS: Array<{ value: VisualEffectKind; label: string }> = [
  { value: 'cinematic', label: 'Cinematográfico' },
  { value: 'warm', label: 'Cálido' },
  { value: 'cool', label: 'Frío' },
  { value: 'black_white', label: 'Blanco y negro' },
  { value: 'vintage', label: 'Vintage' },
  { value: 'vivid', label: 'Colores vivos' }
]

const FILTERS: Record<VisualEffectKind, string> = {
  cinematic: 'contrast(1.15) saturate(0.82) brightness(0.96) hue-rotate(4deg)',
  warm: 'saturate(1.20) hue-rotate(-8deg)',
  cool: 'saturate(0.90) hue-rotate(12deg)',
  black_white: 'grayscale(1) contrast(1.08)',
  vintage: 'sepia(0.55) contrast(0.92) saturate(0.82) brightness(0.96)',
  vivid: 'saturate(1.45) contrast(1.08)'
}

export function visualEffectLabel(kind: VisualEffectKind): string {
  return VISUAL_EFFECT_OPTIONS.find((item) => item.value === kind)?.label ?? kind
}

export function activeVisualEffects(ranges: VisualEffectRange[], sourceTimeS: number): VisualEffectRange[] {
  return ranges.filter((item) => item.startS <= sourceTimeS && sourceTimeS < item.endS)
}

export function visualEffectCss(ranges: VisualEffectRange[], sourceTimeS: number): string {
  return activeVisualEffects(ranges, sourceTimeS).map((item) => FILTERS[item.kind]).join(' ') || 'none'
}
