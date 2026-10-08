import {
  AlertCircle,
  ChevronDown,
  FilePlus2,
  FolderOpen,
  Layers3,
  RefreshCw,
  RotateCcw,
  Server
} from 'lucide-react'
import type { BridgeStatus, RecoveryInfo } from '../../../../shared/contracts'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { CreaSculpture } from './CreaSculpture'
import { cn } from '../../lib/utils'
import './welcome-creator.css'

/**
 * Primera pantalla del recorrido de bienvenida.
 *
 * Contiene lo que antes era todo `WelcomeView`: marca, acciones principales,
 * aviso de recuperación, estado del backend y errores. Se extrajo a su propio
 * componente al convertir la bienvenida en una página desplazable, para que la
 * vista quede como composición de secciones y no como un único bloque largo.
 *
 * Ocupa una pantalla completa (`min-h-screen`) porque marca el punto de partida
 * del desplazamiento: la galería debe quedar justo por debajo del pliegue.
 *
 * La lista compacta de proyectos recientes ya no vive aquí: se movió a
 * `ProjectsGallery`, que es ahora la superficie de recientes.
 */
interface WelcomeHeroProps {
  bridgeStatus: BridgeStatus | null
  recovery: RecoveryInfo | null
  busy: boolean
  error: string | null
  /** Muestra la indicación de desplazamiento solo si hay algo debajo. */
  showScrollHint: boolean
  onNewProject: () => void
  onOpenProject: () => void
  onOpenBatch: () => void
  onRestoreRecovery: () => void
}

export function WelcomeHero({
  bridgeStatus,
  recovery,
  busy,
  error,
  showScrollHint,
  onNewProject,
  onOpenProject,
  onOpenBatch,
  onRestoreRecovery
}: WelcomeHeroProps): React.JSX.Element {
  return (
    <section className="creator-hero">
      <div className="creator-hero__content">
        <div className="creator-hero__masthead hero-in" style={{ '--i': 0 } as React.CSSProperties}>
          <span className="creator-hero__brand">
            CREA<span>cut</span><i />
            <small className="ml-2 rounded border border-current/30 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-[.16em]">
              Beta
            </small>
          </span>
          <span>DE TU IDEA AL ÚLTIMO CORTE</span>
        </div>
        <h1 className="creator-hero__heading hero-in" style={{ '--i': 1 } as React.CSSProperties}>
          Dale forma.
        </h1>
        <CreaSculpture />

        <div className="creator-hero__bottom hero-in" style={{ '--i': 3 } as React.CSSProperties}>
          <div className="creator-hero__copy">
            <p className="creator-hero__eyebrow">TU HISTORIA. TUS DECISIONES.</p>
            <h2>Construye el corte.<br />Conserva el control.</h2>
            <p>Analiza, revisa y exporta.<br />Todo en tu equipo, todo a tu manera.</p>
          </div>
          <div className="creator-hero__actions">
            <Button variant="primary" size="lg" className="creator-hero__primary" onClick={onNewProject} disabled={busy}>
              <FilePlus2 size={18} /> Nuevo proyecto
            </Button>
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="ghost" size="lg" onClick={onOpenProject} disabled={busy}>
                {busy ? <RefreshCw className="animate-spin-slow" size={18} /> : <FolderOpen size={18} />} Abrir proyecto
              </Button>
              <Button variant="ghost" size="lg" onClick={onOpenBatch} disabled={busy}>
                <Layers3 size={18} /> Procesar lote
              </Button>
            </div>
          </div>
        </div>

        <div className="creator-hero__status">
        {recovery && (
          <button
            className="mt-4 flex w-[min(560px,100%)] items-center gap-2.5 rounded-[9px] border border-warning/30 bg-warning/[.08] px-3 py-2.5 text-left text-warning transition-colors hover:bg-warning/[.13]"
            onClick={onRestoreRecovery}
          >
            <RotateCcw size={19} className="shrink-0" />
            <div className="flex flex-col gap-0.5">
              <strong className="text-[11px]">Recuperar cambios de {recovery.projectName}</strong>
              <span className="text-[9px] text-muted-foreground">
                {new Date(recovery.savedAt).toLocaleString()}
              </span>
            </div>
          </button>
        )}

        <Badge
          variant={bridgeStatus ? 'brand' : error ? 'destructive' : 'default'}
          className={cn(
            'hero-in mt-4 rounded-full px-2.5 py-1.5',
            !bridgeStatus && !error && 'text-muted-foreground'
          )}
          style={{ '--i': 4 } as React.CSSProperties}
        >
          {bridgeStatus ? <span className="live-dot" /> : <Server size={15} />}
          {bridgeStatus
            ? `Backend Python ${bridgeStatus.pythonVersion} conectado`
            : error
              ? 'Backend no disponible'
              : 'Conectando con Python…'}
        </Badge>

        {error && (
          <div className="mt-4 flex max-w-[540px] gap-1.5 whitespace-pre-line text-[11px] text-destructive">
            <AlertCircle size={18} className="shrink-0" /> {error}
          </div>
        )}
        </div>
      </div>

      {showScrollHint && (
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 z-[3] flex flex-col items-center gap-1 text-muted-foreground">
          <span className="text-[9px] uppercase tracking-[.14em]">Tus proyectos</span>
          <ChevronDown size={16} className="scroll-hint-arrow" />
        </div>
      )}

    </section>
  )
}
