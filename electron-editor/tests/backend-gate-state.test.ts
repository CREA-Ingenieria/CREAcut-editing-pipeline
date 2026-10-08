import { describe, expect, it } from 'vitest'
import { failedSetupStatus, retryingSetupStatus } from '../src/renderer/src/views/backend-gate-state'

describe('backend-gate-state', () => {
  it('convierte un rechazo en estado failed con su mensaje', () => {
    expect(failedSetupStatus(new Error('IPC caído')).error).toBe('IPC caído')
    expect(failedSetupStatus('boom')).toMatchObject({ state: 'failed', error: 'boom', errorKind: 'start' })
  })

  it('al reintentar vuelve a running sin error ni detalle y conserva el registro', () => {
    const next = retryingSetupStatus({ state: 'failed', steps: [], error: 'x', detail: 'y', logPath: '/log' })
    expect(next).toMatchObject({ state: 'running', logPath: '/log' })
    expect(next.error).toBeUndefined()
    expect(next.detail).toBeUndefined()
    expect(next.steps.every((s) => s.state === 'pending')).toBe(true)
    expect(retryingSetupStatus(null).state).toBe('running')
  })
})
