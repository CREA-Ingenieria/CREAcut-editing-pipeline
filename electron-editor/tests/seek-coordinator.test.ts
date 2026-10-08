import { describe, expect, it } from 'vitest'
import { SeekCoordinator } from '../src/renderer/src/services/seek-coordinator'

describe('SeekCoordinator', () => {
  it('ignora timeupdate antiguos hasta confirmar el destino', () => {
    const coordinator = new SeekCoordinator()
    coordinator.request(18.5)

    expect(coordinator.acceptTimeUpdate(0)).toBe(false)
    expect(coordinator.target()).toBe(18.5)
    expect(coordinator.acceptTimeUpdate(18.46)).toBe(true)
    expect(coordinator.target()).toBeNull()
  })

  it('reintenta cuando seeked termina en una posición incorrecta', () => {
    const coordinator = new SeekCoordinator()
    coordinator.request(42)

    expect(coordinator.retryAfterSeeked(0)).toBe(42)
    expect(coordinator.retryAfterSeeked(42.02)).toBeNull()
    expect(coordinator.target()).toBeNull()
  })

  it('conserva únicamente el salto más reciente', () => {
    const coordinator = new SeekCoordinator()
    coordinator.request(10)
    coordinator.request(25)

    expect(coordinator.targetToApply(0)).toBe(25)
    expect(coordinator.acceptTimeUpdate(10)).toBe(false)
    expect(coordinator.acceptTimeUpdate(25)).toBe(true)
  })

  it('no fuerza un seek cuando el reproductor ya está en el destino', () => {
    const coordinator = new SeekCoordinator()
    coordinator.request(7)

    expect(coordinator.targetToApply(7.005)).toBeNull()
    expect(coordinator.target()).toBeNull()
  })
})
