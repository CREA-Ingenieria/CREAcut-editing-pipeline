import { AlertCircle, Check, ChevronDown, RotateCcw } from 'lucide-react'
import type { BackendSetupStatus, BackendSetupStep } from '../../../shared/backend-setup'
import { Button } from '../components/ui/button'
import { ScrollArea } from '../components/ui/scroll-area'
import { cn } from '../lib/utils'
import '../components/welcome/welcome-creator.css'
import '../components/setup/setup-view.css'

/**
 * Pantalla del primer arranque en macOS, mientras se arma el entorno Python.
 *
 * Es presentacional: el estado lo mantiene el proceso main y lo trae
 * `BackendGate`. Reutiliza la superficie de la bienvenida (auroras, retícula,
 * cabecera de marca y entrada escalonada) para que se lea como parte de
 * CREAcut y no como un instalador genérico.
 */
interface SetupViewProps {
  status: BackendSetupStatus
  showDetail: boolean
  onRetry: () => void
  onToggleDetail: () => void
}

const STATE_TEXT: Record<BackendSetupStep['state'], string> = {
  pending: 'pendiente',
  running: 'en curso',
  done: 'listo',
  failed: 'con error'
}

/** Consejo tras el error: Gatekeeper si macOS no dejó ejecutar uv o Python, red y disco en lo demás. */
const ADVICE: Record<'launch' | 'other', string> = {
  launch: 'Abre Ajustes del Sistema → Privacidad y seguridad y permite CREAcut; luego vuelve a intentarlo.',
  other: 'Revisa la conexión y el espacio libre, y vuelve a intentarlo.'
}

/** Resumen para lectores de pantalla: solo cambia cuando cambia el estado de un paso. */
function stepsSummary(steps: BackendSetupStep[]): string {
  return steps.map((step) => `${step.label}: ${STATE_TEXT[step.state]}.`).join(' ')
}

function StepIcon({ step }: { step: BackendSetupStep }): React.JSX.Element {
  if (step.state === 'done') return <Check size={15} className="setup-step__icon setup-step__icon--done" aria-hidden />
  if (step.state === 'failed') return <AlertCircle size={15} className="setup-step__icon setup-step__icon--failed" aria-hidden />
  if (step.state === 'running') return <span className="live-dot setup-step__icon" aria-hidden />
  return <span className="setup-step__pending" aria-hidden />
}

/** Superficie de la bienvenida: auroras y retícula detrás del panel. */
function SetupSurface(): React.JSX.Element {
  return (
    <div aria-hidden className="hero-surface fixed inset-0 -z-10 overflow-hidden">
      <span className="fx-aurora fx-aurora--a" />
      <span className="fx-aurora fx-aurora--b" />
      <span className="fx-aurora fx-aurora--c" />
      <span className="fx-grid absolute inset-0" />
    </div>
  )
}

function Masthead(): React.JSX.Element {
  return (
    <div className="creator-hero__masthead hero-in" style={{ '--i': 0 } as React.CSSProperties}>
      <span className="creator-hero__brand">
        CREA<span>cut</span><i />
        <small className="ml-2 rounded border border-current/30 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-[.16em]">
          Beta
        </small>
      </span>
      <span>DE TU IDEA AL ÚLTIMO CORTE</span>
    </div>
  )
}

/**
 * Lo que se ve mientras main comprueba que el entorno sirve (en macOS importa
 * torch y compañía en cada arranque). Mismo vocabulario que la preparación,
 * sin pasos: solo marca y barra indeterminada.
 */
export function LaunchView(): React.JSX.Element {
  return (
    <main className="setup-view">
      <SetupSurface />
      <section className="setup-view__panel">
        <Masthead />
        <h1 className="setup-view__title hero-in" style={{ '--i': 1 } as React.CSSProperties}>
          Abriendo CREAcut…
        </h1>
        <div className="setup-view__progress hero-in" style={{ '--i': 2 } as React.CSSProperties}>
          <div className="setup-progress">
            <div className="busy-bar" role="status" aria-label="Comprobando que todo esté listo" />
          </div>
          <p className="setup-view__hint">Comprobando que todo esté listo.</p>
        </div>
      </section>
    </main>
  )
}

export function SetupView({ status, showDetail, onRetry, onToggleDetail }: SetupViewProps): React.JSX.Element {
  const failed = status.state === 'failed'
  const current = status.steps.find((step) => step.state === 'running')
  const percent = current?.percent

  return (
    <main className="setup-view">
      <SetupSurface />

      <section className="setup-view__panel">
        <Masthead />

        <h1 className="setup-view__title hero-in" style={{ '--i': 1 } as React.CSSProperties}>
          Preparando CREAcut para tu Mac
        </h1>
        <p className="setup-view__lead hero-in" style={{ '--i': 2 } as React.CSSProperties}>
          La primera vez descargamos lo que CREAcut necesita para trabajar sin conexión: unos 5 GB.
          Solo pasa una vez.
        </p>

        {/* La región viva anuncia el estado de los pasos; las líneas de uv
            cambian varias veces por segundo y no se anuncian. */}
        <p className="sr-only" aria-live="polite">{stepsSummary(status.steps)}</p>

        <ol
          className="setup-steps hero-in"
          style={{ '--i': 3 } as React.CSSProperties}
          aria-label="Pasos de la preparación"
        >
          {status.steps.map((step) => (
            <li key={step.id} className="setup-step" data-state={step.state}>
              <StepIcon step={step} />
              <div className="setup-step__body">
                <span className="setup-step__label">
                  {step.label}
                  <span className="sr-only">: {STATE_TEXT[step.state]}</span>
                </span>
                {step.message && step.state !== 'pending' && (
                  <span className="setup-step__message">{step.message}</span>
                )}
              </div>
              {step.state === 'running' && step.percent !== undefined && (
                <span className="setup-step__percent">{step.percent}%</span>
              )}
            </li>
          ))}
        </ol>

        {!failed && (
          <div className="setup-view__progress hero-in" style={{ '--i': 4 } as React.CSSProperties}>
            {percent !== undefined ? (
              <div
                className="setup-progress"
                role="progressbar"
                aria-label={current?.label}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
              >
                <span style={{ width: `${percent}%` }} />
              </div>
            ) : (
              <div className="setup-progress">
                <div className="busy-bar" role="status" aria-label="Preparación en curso" />
              </div>
            )}
            <p className="setup-view__hint">
              Mantén la conexión a Internet. Puedes dejar esta ventana abierta y seguir con otra cosa.
            </p>
          </div>
        )}

        {failed && (
          <div className="setup-view__error" role="alert">
            <p>
              <AlertCircle size={16} className="shrink-0" aria-hidden />
              <span>{status.error} {ADVICE[status.errorKind === 'launch' ? 'launch' : 'other']}</span>
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" size="lg" onClick={onRetry} autoFocus>
                <RotateCcw size={16} /> Reintentar
              </Button>
              {status.detail && (
                <Button variant="ghost" size="lg" onClick={onToggleDetail} aria-expanded={showDetail}>
                  <ChevronDown size={16} className={cn('transition-transform', showDetail && 'rotate-180')} /> Ver detalle
                </Button>
              )}
            </div>
            {showDetail && status.detail && (
              <ScrollArea className="setup-view__detail">
                <pre>{status.detail}</pre>
              </ScrollArea>
            )}
            {status.logPath && <p className="setup-view__log">Registro completo: {status.logPath}</p>}
          </div>
        )}
      </section>
    </main>
  )
}
