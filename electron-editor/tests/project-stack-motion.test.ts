import { describe, expect, it } from 'vitest'
import { computeStackLayout } from '../src/renderer/src/services/project-stack-motion'

// Tres tarjetas de 600 px separadas por 12vh (108 px) en una ventana de 900 px.
const base = {
  viewportHeight: 900,
  slotTops: [900, 1608, 2316],
  slotHeights: [600, 600, 600],
  slotMargins: [108, 108, 0],
  stackBottom: 2916
}

describe('computeStackLayout', () => {
  it('no apila con menos de dos ranuras', () => {
    expect(computeStackLayout({ ...base, slotTops: [900], slotHeights: [600], slotMargins: [0], stackBottom: 1500 })).toBeNull()
  })

  it('reproduce los tramos que calculaba ScrollTrigger', () => {
    const layout = computeStackLayout(base)!
    expect(layout.step).toBe(28)
    expect(layout.end).toBe(2188)
    expect(layout.slots.map((slot) => slot.top)).toEqual([72, 100])
    expect(layout.slots.map((slot) => slot.start)).toEqual([828, 1508])
    expect(layout.slots[0].scale).toBeCloseTo(0.94)
    expect(layout.slots[1].scale).toBeCloseTo(0.97)
  })

  it('alarga cada pista lo que dura su tramo sin cambiar el largo de la página', () => {
    const layout = computeStackLayout(base)!
    layout.slots.forEach((slot, index) => {
      expect(slot.trackHeight + slot.trackMargin).toBe(base.slotHeights[index] + base.slotMargins[index])
    })
    expect(layout.slots[0].trackHeight).toBe(600 + (2188 - 828))
    expect(layout.slots[1].trackHeight).toBe(600 + (2188 - 1508))
  })

  it('acota el escalonado entre 0 y 28 px', () => {
    expect(computeStackLayout({ ...base, viewportHeight: 700, slotHeights: [650, 650, 650] })!.step).toBe(0)
    expect(computeStackLayout({ ...base, viewportHeight: 2000 })!.step).toBe(28)
  })

  it('no encoge una tarjeta por debajo de .79', () => {
    const count = 10
    const layout = computeStackLayout({
      viewportHeight: 900,
      slotTops: Array.from({ length: count }, (_, index) => 900 + index * 708),
      slotHeights: Array<number>(count).fill(600),
      slotMargins: [...Array<number>(count - 1).fill(108), 0],
      stackBottom: 900 + (count - 1) * 708 + 600
    })!
    expect(layout.slots).toHaveLength(count - 1)
    expect(layout.slots[0].scale).toBe(0.79)
  })

  it('no alarga la pista cuando el tramo no existe', () => {
    const layout = computeStackLayout({ ...base, stackBottom: 1000 })!
    expect(layout.slots[0].trackHeight).toBe(600)
    expect(layout.slots[0].trackMargin).toBe(108)
  })
})
