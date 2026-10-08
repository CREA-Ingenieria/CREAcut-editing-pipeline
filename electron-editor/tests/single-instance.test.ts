import { describe, expect, it, vi } from 'vitest'
import { setupSingleInstance } from '../src/main/single-instance'

describe('setupSingleInstance', () => {
  it('rechaza el segundo proceso antes de registrar ventanas', () => {
    const onSecondInstance = vi.fn()

    expect(setupSingleInstance(() => false, onSecondInstance, () => null)).toBe(false)
    expect(onSecondInstance).not.toHaveBeenCalled()
  })

  it('enfoca la ventana existente cuando se intenta abrir otra instancia', () => {
    let secondInstanceListener: (() => void) | null = null
    const window = {
      isMinimized: vi.fn(() => true),
      restore: vi.fn(),
      show: vi.fn(),
      focus: vi.fn()
    }

    const acquired = setupSingleInstance(
      () => true,
      (listener) => { secondInstanceListener = listener },
      () => window
    )
    secondInstanceListener?.()

    expect(acquired).toBe(true)
    expect(window.restore).toHaveBeenCalledOnce()
    expect(window.show).toHaveBeenCalledOnce()
    expect(window.focus).toHaveBeenCalledOnce()
  })

  it('no intenta restaurar una ventana que no está minimizada', () => {
    let secondInstanceListener: (() => void) | null = null
    const window = {
      isMinimized: vi.fn(() => false),
      restore: vi.fn(),
      show: vi.fn(),
      focus: vi.fn()
    }

    setupSingleInstance(
      () => true,
      (listener) => { secondInstanceListener = listener },
      () => window
    )
    secondInstanceListener?.()

    expect(window.restore).not.toHaveBeenCalled()
    expect(window.show).toHaveBeenCalledOnce()
    expect(window.focus).toHaveBeenCalledOnce()
  })
})
