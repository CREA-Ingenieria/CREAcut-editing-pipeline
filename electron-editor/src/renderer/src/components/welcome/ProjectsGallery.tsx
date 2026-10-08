import { useMemo, useRef, useState } from 'react'
import type { RecentProject } from '../../../../shared/contracts'
import { useProjectStack } from '../../hooks/useProjectStack'
import { buildGalleryTiles, galleryTilesSignature } from '../../services/gallery-layout'
import { ProjectGalleryTile } from './ProjectGalleryTile'
import './project-portfolio.css'

/**
 * Sección "Proyectos recientes" de la pantalla de bienvenida.
 *
 * Es la superficie de proyectos recientes: sustituye a la lista compacta que
 * antes vivía dentro del héroe y conserva su comportamiento (un clic abre el
 * proyecto por su ruta). Las tarjetas se apilan con el desplazamiento vertical.
 *
 * El componente es presentacional: recibe los proyectos ya cargados y un
 * callback. No conoce IPC, ni el backend, ni cómo se abren los proyectos.
 */
interface ProjectsGalleryProps {
  projects: RecentProject[]
  busy: boolean
  error: string | null
  onOpenProjectPath: (path: string) => Promise<void>
}

export function ProjectsGallery({
  projects,
  busy,
  error,
  onOpenProjectPath
}: ProjectsGalleryProps): React.JSX.Element {
  const tiles = useMemo(() => buildGalleryTiles(projects), [projects])
  const signature = useMemo(() => galleryTilesSignature(tiles), [tiles])

  const { stackRef, revealFocusedCard } = useProjectStack(signature)
  const openingRef = useRef(false)
  const [openingPath, setOpeningPath] = useState<string | null>(null)
  const [attemptedPath, setAttemptedPath] = useState<string | null>(null)

  async function open(path: string): Promise<void> {
    if (busy || openingRef.current) return
    openingRef.current = true
    setOpeningPath(path)
    setAttemptedPath(path)
    try {
      await onOpenProjectPath(path)
    } finally {
      openingRef.current = false
      setOpeningPath(null)
    }
  }

  return (
    <section id="portfolio" className="project-portfolio" aria-labelledby="gallery-title">
      <header className="project-portfolio__heading">
        <div className="project-portfolio__eyebrow"><span>TU TRABAJO, EN PRIMER PLANO</span><span>{String(tiles.length).padStart(2, '0')} PROYECTOS</span></div>
        <h2 id="gallery-title">Proyectos<span>.</span></h2>
        <p>Cada idea tiene su historia. Continúa donde la dejaste.</p>
      </header>
      <div className="project-portfolio__stack" ref={stackRef}>
        {tiles.map((tile, index) => (
          <div key={tile.key} data-project-slot className="project-portfolio__slot" style={{ zIndex: index + 1 }}
            onFocusCapture={(event) => {
              if ((event.target as HTMLElement).matches(':focus-visible')) revealFocusedCard(index)
            }}>
            <ProjectGalleryTile tile={tile} index={index} onOpen={(path) => void open(path)}
              disabled={busy || openingPath !== null} opening={openingPath === tile.project.path}
              error={attemptedPath === tile.project.path ? error : null} />
          </div>
        ))}
      </div>
      <footer className="project-portfolio__footer"><span>HECHO CON CREA</span><span>El próximo corte empieza contigo.</span></footer>
    </section>
  )
}
