import { initialSetupSteps, type BackendSetupStatus } from '../../../shared/backend-setup'

/** Estado de fallo cuando el propio IPC rechaza (no hay detalle del orquestador). */
export function failedSetupStatus(reason: unknown): BackendSetupStatus {
  return {
    state: 'failed',
    steps: initialSetupSteps(),
    error: reason instanceof Error ? reason.message : String(reason),
    errorKind: 'start'
  }
}

/** Estado optimista al pulsar Reintentar: quita el error y el botón al instante.
 *  Main emitirá el estado real al arrancar. */
export function retryingSetupStatus(previous: BackendSetupStatus | null): BackendSetupStatus {
  return { state: 'running', steps: initialSetupSteps(), logPath: previous?.logPath }
}
