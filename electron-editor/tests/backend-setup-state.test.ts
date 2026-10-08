import { describe, expect, it } from 'vitest'
import {
  applySetupProgress,
  initialSetupSteps,
  parseWhisperPercent,
  readySetupStatus,
  SETUP_STEP_IDS,
  type BackendSetupStatus
} from '../src/shared/backend-setup'

const running = (): BackendSetupStatus => ({ state: 'running', steps: initialSetupSteps() })

describe('estado de la preparación', () => {
  it('empieza con los cinco pasos pendientes y en orden', () => {
    expect(SETUP_STEP_IDS).toEqual(['python', 'torch', 'dependencies', 'verify', 'whisper'])
    expect(initialSetupSteps().map((step) => [step.id, step.label, step.state])).toEqual([
      ['python', 'Python 3.12', 'pending'],
      ['torch', 'PyTorch', 'pending'],
      ['dependencies', 'Dependencias', 'pending'],
      ['verify', 'Comprobación', 'pending'],
      ['whisper', 'Whisper', 'pending']
    ])
  })

  it('el estado listo marca todos los pasos como hechos', () => {
    const ready = readySetupStatus()
    expect(ready.state).toBe('ready')
    expect(ready.steps.every((step) => step.state === 'done')).toBe(true)
  })

  it('actualiza solo el paso del evento y no muta el estado anterior', () => {
    const before = running()
    const after = applySetupProgress(before, { stepId: 'torch', state: 'running', message: 'Resolved 12 packages' })
    expect(after.steps[1]).toMatchObject({ id: 'torch', state: 'running', message: 'Resolved 12 packages' })
    expect(after.steps[0].state).toBe('pending')
    expect(before.steps[1].state).toBe('pending')
  })

  it('conserva el último mensaje si un evento llega sin mensaje', () => {
    const withMessage = applySetupProgress(running(), { stepId: 'python', state: 'running', message: 'Using CPython 3.12.9' })
    const done = applySetupProgress(withMessage, { stepId: 'python', state: 'done' })
    expect(done.steps[0]).toMatchObject({ state: 'done', message: 'Using CPython 3.12.9' })
  })

  it('un paso fallido deja la preparación en failed', () => {
    const failed = applySetupProgress(running(), { stepId: 'verify', state: 'failed', message: 'El entorno quedó incompleto.' })
    expect(failed.state).toBe('failed')
    expect(failed.steps[3].state).toBe('failed')
  })

  it('reconoce el porcentaje de descarga de Whisper', () => {
    expect(parseWhisperPercent('large-v3.pt: 42%')).toBe(42)
    expect(parseWhisperPercent('medium.pt: 100%')).toBe(100)
    expect(parseWhisperPercent('Descargando large-v3.pt...')).toBeUndefined()
    expect(parseWhisperPercent('large-v3.pt: 1536 MB')).toBeUndefined()
  })
})
