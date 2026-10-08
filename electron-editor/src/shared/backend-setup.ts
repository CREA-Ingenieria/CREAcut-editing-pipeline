/**
 * Estado de la preparación del primer arranque en macOS.
 *
 * Lo comparten el proceso main, que lo mantiene, y el renderer, que lo
 * muestra. Solo contiene tipos y funciones puras: nada de Electron ni de Node.
 */
export type BackendSetupStepId = 'python' | 'torch' | 'dependencies' | 'verify' | 'whisper'
export type BackendSetupStepState = 'pending' | 'running' | 'done' | 'failed'
export type BackendSetupState = 'ready' | 'needs-setup' | 'running' | 'failed'
/**
 * Qué clase de fallo fue, para dar el consejo correcto:
 * - `launch`: macOS no dejó ejecutar uv o el Python del entorno (Gatekeeper).
 * - `step`: un paso corrió y terminó mal (red, espacio, dependencias).
 * - `start`: la preparación ni siquiera pudo empezar.
 */
export type BackendSetupErrorKind = 'launch' | 'step' | 'start'

export interface BackendSetupStep {
  id: BackendSetupStepId
  label: string
  state: BackendSetupStepState
  /** Última línea útil del paso. */
  message?: string
  /** Solo Whisper informa porcentaje. */
  percent?: number
}

export interface BackendSetupStatus {
  state: BackendSetupState
  steps: BackendSetupStep[]
  error?: string
  errorKind?: BackendSetupErrorKind
  /** Últimas líneas del registro cuando algo falla. */
  detail?: string
  logPath?: string
}

export interface BackendSetupProgress {
  stepId: BackendSetupStepId
  state: BackendSetupStepState
  message?: string
  percent?: number
}

export const SETUP_STEP_IDS: BackendSetupStepId[] = ['python', 'torch', 'dependencies', 'verify', 'whisper']

const STEP_LABELS: Record<BackendSetupStepId, string> = {
  python: 'Python 3.12',
  torch: 'PyTorch',
  dependencies: 'Dependencias',
  verify: 'Comprobación',
  whisper: 'Whisper'
}

export function initialSetupSteps(): BackendSetupStep[] {
  return SETUP_STEP_IDS.map((id) => ({ id, label: STEP_LABELS[id], state: 'pending' }))
}

export function readySetupStatus(): BackendSetupStatus {
  return { state: 'ready', steps: initialSetupSteps().map((step) => ({ ...step, state: 'done' })) }
}

export function applySetupProgress(status: BackendSetupStatus, event: BackendSetupProgress): BackendSetupStatus {
  const steps = status.steps.map((step) => step.id !== event.stepId ? step : {
    ...step,
    state: event.state,
    message: event.message ?? step.message,
    percent: event.percent ?? (event.state === 'running' ? step.percent : undefined)
  })
  return { ...status, steps, state: event.state === 'failed' ? 'failed' : status.state }
}

/** `setup_models.download` informa líneas como `large-v3.pt: 42%`. */
export function parseWhisperPercent(line: string): number | undefined {
  const match = /:\s*(\d{1,3})%\s*$/.exec(line)
  if (!match) return undefined
  const value = Number(match[1])
  return value >= 0 && value <= 100 ? value : undefined
}
