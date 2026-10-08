import { useId, useState } from 'react'
import { ArrowUpRight, FolderOpen, LoaderCircle } from 'lucide-react'
import type { RecentProject } from '../../../../shared/contracts'
import { compactPath, formatRelativeDate } from '../../format'
import type { GalleryTile } from '../../services/gallery-layout'

type PreviewImage = NonNullable<RecentProject['previewImages']>[number]

function ProjectArtwork({ image, variant, name, number }: {
  image?: PreviewImage; variant: 'detail' | 'identity' | 'cover'; name: string; number: string
}): React.JSX.Element {
  const [failed, setFailed] = useState(false)
  const hasImage = image && !failed
  return (
    <figure className={`portfolio-art portfolio-art--${variant}`} data-image={Boolean(hasImage)}>
      {hasImage ? (
        <img src={image.url} alt={`${image.label} de ${name}`} loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <div className="portfolio-art__graphic" aria-hidden>
          <span className="portfolio-art__orb" />
          <span className="portfolio-art__ring" />
          <span className="portfolio-art__type">{variant === 'identity' ? number : variant === 'detail' ? 'C' : 'CREA'}</span>
          {variant === 'cover' && <span className="portfolio-art__name">{name}</span>}
          <span className="portfolio-art__cross">+</span>
        </div>
      )}
      <figcaption>{hasImage ? image.label : variant === 'cover' ? 'Portada del proyecto' : 'CREAcut · Estudio local'}</figcaption>
    </figure>
  )
}

interface ProjectGalleryTileProps {
  tile: GalleryTile
  index: number
  onOpen: (path: string) => void
  disabled: boolean
  opening: boolean
  error: string | null
}

export function ProjectGalleryTile({ tile, index, onOpen, disabled, opening, error }: ProjectGalleryTileProps): React.JSX.Element {
  const { name, path, openedAt, previewImages = [] } = tile.project
  const titleId = useId()
  const number = String(index + 1).padStart(2, '0')
  const [cover, detail, identity] = previewImages

  return (
    <article className="portfolio-project" data-project-card data-accent={tile.accent} aria-labelledby={titleId}>
      <header className="portfolio-project__header">
        <span className="portfolio-project__number" aria-hidden>{number}</span>
        <div className="portfolio-project__title">
          <span className="portfolio-project__category">PROYECTO LOCAL <i /> {formatRelativeDate(openedAt)}</span>
          <h3 id={titleId} title={name}>{name}</h3>
        </div>
        <button type="button" className="portfolio-project__open" onClick={() => onOpen(path)} disabled={disabled} aria-busy={opening} aria-label={opening ? `Abriendo ${name}` : `Abrir proyecto ${name}`}>
          {opening ? <>Abriendo… <LoaderCircle size={19} className="animate-spin" /></> : <>Abrir proyecto <ArrowUpRight size={19} /></>}
        </button>
      </header>
      {error && <div role="alert" className="portfolio-project__error">{error}</div>}
      <div className="portfolio-project__collage">
        <div className="portfolio-project__details">
          <ProjectArtwork key={detail?.url ?? 'detail'} image={detail} variant="detail" name={name} number={number} />
          <ProjectArtwork key={identity?.url ?? 'identity'} image={identity} variant="identity" name={name} number={number} />
        </div>
        <ProjectArtwork key={cover?.url ?? 'cover'} image={cover} variant="cover" name={name} number={number} />
      </div>
      <footer className="portfolio-project__footer"><FolderOpen size={13} /><span title={path}>{compactPath(path)}</span><span>CREA / {number}</span></footer>
    </article>
  )
}
