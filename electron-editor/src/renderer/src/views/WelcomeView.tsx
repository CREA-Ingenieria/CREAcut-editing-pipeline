import { useRef } from 'react'
import type { BridgeStatus, RecentProject, RecoveryInfo } from '../../../shared/contracts'
import { ProjectsGallery } from '../components/welcome/ProjectsGallery'
import { ThemeButton } from '../components/ThemeButton'
import { WelcomeHero } from '../components/welcome/WelcomeHero'
import { WorkflowSection } from '../components/welcome/WorkflowSection'
import { useSmoothScroller } from '../hooks/useSmoothScroller'
import type { ThemeMode } from '../types/editor'

/**
 * Pantalla de entrada, ahora como página desplazable.
 *
 * Composición de tres secciones:
 *
 *   1. `WelcomeHero`      — marca, acciones y estado del backend (una pantalla);
 *   2. `ProjectsGallery`  — portafolio de proyectos con tarjetas apiladas;
 *   3. `WorkflowSection`  — resumen del pipeline y atajos.
 *
 * El contenido se desplaza con el scroll del propio documento, suavizado por
 * `useSmoothScroller`, que explica por qué eso obliga a liberar temporalmente
 * el bloqueo de desplazamiento del documento y cómo se acota a esta vista.
 *
 * El botón de tema y el telón de fondo quedan fuera del contenido: son fijos a
 * la ventana y no forman parte de lo que se desplaza.
 */
interface WelcomeViewProps {
  bridgeStatus: BridgeStatus | null
  recentProjects: RecentProject[]
  recovery: RecoveryInfo | null
  busy: boolean
  error: string | null
  theme: ThemeMode
  onToggleTheme: () => void
  onNewProject: () => void
  onOpenProject: () => void
  onOpenProjectPath: (path: string) => Promise<void>
  onOpenBatch: () => void
  onRestoreRecovery: () => void
}

export function WelcomeView({
  bridgeStatus,
  recentProjects,
  recovery,
  busy,
  error,
  theme,
  onToggleTheme,
  onNewProject,
  onOpenProject,
  onOpenProjectPath,
  onOpenBatch,
  onRestoreRecovery
}: WelcomeViewProps): React.JSX.Element {
  const contentRef = useRef<HTMLDivElement>(null)
  const hasProjects = recentProjects.length > 0

  useSmoothScroller({ contentRef })

  return (
    <>
      <div className="fixed right-4.5 top-4.5 z-[6]">
        <ThemeButton theme={theme} onToggle={onToggleTheme} />
      </div>

      {/* Telon de fondo, fijo a la ventana y por detras del contenido.
          Las tres auroras solo existen en la bienvenida; mantenerlas durante la
          edicion competiria por la GPU justo con la reproduccion de video. */}
      <div aria-hidden className="hero-surface fixed inset-0 -z-10 overflow-hidden">
        <span className="fx-aurora fx-aurora--a" />
        <span className="fx-aurora fx-aurora--b" />
        <span className="fx-aurora fx-aurora--c" />
        <span className="fx-grid absolute inset-0" />
      </div>

      <div ref={contentRef}>
        <WelcomeHero
          bridgeStatus={bridgeStatus}
          recovery={recovery}
          busy={busy}
          error={error}
          showScrollHint={hasProjects}
          onNewProject={onNewProject}
          onOpenProject={onOpenProject}
          onOpenBatch={onOpenBatch}
          onRestoreRecovery={onRestoreRecovery}
        />

        {hasProjects && (
          <ProjectsGallery projects={recentProjects} busy={busy} error={error} onOpenProjectPath={onOpenProjectPath} />
        )}

        {hasProjects && <WorkflowSection />}
      </div>
    </>
  )
}
