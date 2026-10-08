export interface ExistingAppWindow {
  isMinimized: () => boolean
  restore: () => void
  show: () => void
  focus: () => void
}

/**
 * Acquires the Electron single-instance lock before any window/session starts.
 * A second launch focuses the existing window instead of opening Chromium
 * processes that compete for Cache and GPUCache.
 */
export function setupSingleInstance(
  requestLock: () => boolean,
  onSecondInstance: (listener: () => void) => void,
  getWindow: () => ExistingAppWindow | null
): boolean {
  if (!requestLock()) return false

  onSecondInstance(() => {
    const window = getWindow()
    if (!window) return
    if (window.isMinimized()) window.restore()
    window.show()
    window.focus()
  })
  return true
}
