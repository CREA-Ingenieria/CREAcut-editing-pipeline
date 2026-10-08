import { useEffect, useState } from 'react'
import type { BackendSetupStatus } from '../../../shared/backend-setup'
import { creacutService } from '../services/creacut-service'
import { LaunchView, SetupView } from './SetupView'
import { failedSetupStatus, retryingSetupStatus } from './backend-gate-state'

/**
 * Monta la aplicación solo cuando el backend tiene su entorno listo.
 *
 * En macOS empaquetado, el primer arranque arma el entorno Python desde PyPI;
 * mientras tanto se muestra `SetupView` y `App` no existe, así que nadie llama
 * al bridge antes de tiempo. En Windows y en desarrollo el estado llega `ready`
 * en la primera respuesta y la app aparece como siempre.
 */
/** En Windows y desarrollo la respuesta llega antes: así no parpadea «Abriendo CREAcut…». */
const LAUNCH_VIEW_DELAY_MS = 300

export function BackendGate({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [status, setStatus] = useState<BackendSetupStatus | null>(null)
  const [showDetail, setShowDetail] = useState(false)
  const [launchVisible, setLaunchVisible] = useState(false)

  // Un rechazo del IPC se muestra como fallo, con Reintentar disponible.
  const fail = (reason: unknown): void => setStatus(failedSetupStatus(reason))

  useEffect(() => {
    // Mismo tema que eligió la persona en la app; App lo vuelve a aplicar al montarse.
    document.documentElement.dataset.theme =
      window.localStorage.getItem('creacut-theme') === 'light' ? 'light' : 'dark'

    creacutService.onBackendSetupProgress(setStatus)
    creacutService.backendSetupStatus()
      .then((current) => {
        setStatus(current)
        // La preparación arranca sola: no hay nada que decidir antes.
        if (current.state === 'needs-setup') return creacutService.startBackendSetup().then(setStatus).catch(fail)
        return undefined
      })
      .catch(fail)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => setLaunchVisible(true), LAUNCH_VIEW_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [])

  if (status?.state === 'ready') return <>{children}</>
  // Antes de la primera respuesta: fondo de la app y, si la comprobación se
  // alarga (macOS verifica el entorno en cada arranque), «Abriendo CREAcut…».
  if (!status) return launchVisible ? <LaunchView /> : <div className="h-full w-full bg-[var(--bg)]" />

  return (
    <SetupView
      status={status}
      showDetail={showDetail}
      onRetry={() => {
        setShowDetail(false)
        // Respuesta inmediata: main emitirá el estado real al arrancar.
        setStatus((previous) => retryingSetupStatus(previous))
        void creacutService.startBackendSetup().then(setStatus).catch(fail)
      }}
      onToggleDetail={() => setShowDetail((value) => !value)}
    />
  )
}
