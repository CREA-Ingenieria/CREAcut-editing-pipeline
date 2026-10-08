const APPLY_TOLERANCE_S = 0.01
const EVENT_TOLERANCE_S = 0.08

/**
 * Keeps a requested source seek alive until Chromium confirms it. Media
 * elements can emit stale `timeupdate` events while a seek is in flight; those
 * events must not move the UI back to the previous position.
 */
export class SeekCoordinator {
  private pendingTargetS: number | null = null

  request(targetS: number): void {
    this.pendingTargetS = targetS
  }

  clear(): void {
    this.pendingTargetS = null
  }

  target(): number | null {
    return this.pendingTargetS
  }

  targetToApply(currentTimeS: number): number | null {
    const target = this.pendingTargetS
    if (target === null) return null
    if (Math.abs(currentTimeS - target) <= APPLY_TOLERANCE_S) {
      this.pendingTargetS = null
      return null
    }
    return target
  }

  /** Returns false for stale time updates produced before the requested seek. */
  acceptTimeUpdate(currentTimeS: number): boolean {
    const target = this.pendingTargetS
    if (target === null) return true
    if (Math.abs(currentTimeS - target) > EVENT_TOLERANCE_S) return false
    this.pendingTargetS = null
    return true
  }

  /** Returns a target when Chromium reported `seeked` at the wrong position. */
  retryAfterSeeked(currentTimeS: number): number | null {
    const target = this.pendingTargetS
    if (target === null) return null
    if (Math.abs(currentTimeS - target) <= EVENT_TOLERANCE_S) {
      this.pendingTargetS = null
      return null
    }
    return target
  }
}
