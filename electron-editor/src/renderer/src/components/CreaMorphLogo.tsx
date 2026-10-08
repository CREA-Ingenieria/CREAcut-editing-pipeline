import { useEffect, useId, useState, type CSSProperties, type KeyboardEvent, type SVGProps } from 'react'

interface CreaMorphLogoProps {
  className?: string
}

type SymbolProps = SVGProps<SVGGElement> & { 'data-flipped': 'true' | 'false' }

function symbolDelay(index: number): CSSProperties {
  return { '--symbol-delay': `${index * 115}ms` } as CSSProperties
}

/**
 * CREA wordmark introduced by its four geometric identities. The transition
 * is native SVG/CSS, without an animation library or a proprietary morphing
 * plugin.
 *
 * Once the intro settles each symbol becomes a toggle: every time the pointer
 * enters it — or it is activated from the keyboard — it flips between its
 * shape and its letter and stays there, so sweeping across CREA flips the
 * letters the pointer crossed and sweeping again brings them back.
 */
export function CreaMorphLogo({ className }: CreaMorphLogoProps): React.JSX.Element {
  const id = useId().replace(/:/g, '')
  const [interactive, setInteractive] = useState(false)
  const [flipped, setFlipped] = useState<boolean[]>([false, false, false, false])

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setInteractive(true)
      return
    }
    const timer = window.setTimeout(() => setInteractive(true), 2200)
    return () => window.clearTimeout(timer)
  }, [])

  function toggle(index: number): void {
    if (!interactive) return
    setFlipped((current) => current.map((value, position) => (position === index ? !value : value)))
  }

  function symbolProps(index: number): SymbolProps {
    return {
      role: 'button',
      tabIndex: 0,
      'aria-pressed': flipped[index],
      'data-flipped': flipped[index] ? 'true' : 'false',
      style: symbolDelay(index),
      onMouseEnter: () => toggle(index),
      onClick: () => toggle(index),
      onKeyDown: (event: KeyboardEvent<SVGGElement>) => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        toggle(index)
      }
    }
  }

  return (
    <svg
      className={[
        'crea-morph',
        interactive && 'crea-morph--interactive',
        className
      ].filter(Boolean).join(' ')}
      viewBox="0 0 760 240"
      role="group"
      aria-labelledby={`${id}-title ${id}-description`}
      style={{ '--crea-metal-fill': `url(#${id}-metal)` } as CSSProperties}
    >
      <defs>
        <linearGradient id={`${id}-metal`} x1="0" y1="0" x2="0.3" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="32%" stopColor="#d9e5ed" />
          <stop offset="49%" stopColor="#748293" />
          <stop offset="52%" stopColor="#f4f8fb" />
          <stop offset="76%" stopColor="#b5c3d2" />
          <stop offset="100%" stopColor="#596d83" />
        </linearGradient>
      </defs>
      <title id={`${id}-title`}>CREA</title>
      <desc id={`${id}-description`}>
        Círculo, rombo, rectángulo y triángulo se transforman en las letras CREA.
      </desc>

      <ellipse className="crea-morph__halo" cx="380" cy="122" rx="330" ry="98" />

      <g
        className="crea-morph__symbol crea-morph__symbol--c"
        data-shape="circle"
        aria-label="C, círculo"
        {...symbolProps(0)}
        transform="translate(125 118)"
      >
        <rect className="crea-morph__hit" x="-85" y="-86" width="170" height="172" />
        <circle className="crea-morph__shape crea-morph__shape--solid" r="70" />
        <text className="crea-morph__letter" x="0" y="51" textAnchor="middle">C</text>
      </g>

      <g
        className="crea-morph__symbol crea-morph__symbol--r"
        data-shape="diamond"
        aria-label="R, rombo"
        {...symbolProps(1)}
        transform="translate(295 118)"
      >
        <rect className="crea-morph__hit" x="-85" y="-86" width="170" height="172" />
        <polygon
          className="crea-morph__shape crea-morph__shape--solid"
          points="0,-70 70,0 0,70 -70,0"
        />
        <text className="crea-morph__letter" x="0" y="51" textAnchor="middle">R</text>
      </g>

      <g
        className="crea-morph__symbol crea-morph__symbol--e"
        data-shape="rectangle"
        aria-label="E, rectángulo"
        {...symbolProps(2)}
        transform="translate(465 118)"
      >
        <rect className="crea-morph__hit" x="-85" y="-86" width="170" height="172" />
        <rect
          className="crea-morph__shape crea-morph__shape--solid"
          x="-65"
          y="-57"
          width="130"
          height="114"
          rx="7"
        />
        <text className="crea-morph__letter" x="0" y="51" textAnchor="middle">E</text>
      </g>

      <g
        className="crea-morph__symbol crea-morph__symbol--a"
        data-shape="triangle"
        aria-label="A, triángulo"
        {...symbolProps(3)}
        transform="translate(635 118)"
      >
        <rect className="crea-morph__hit" x="-85" y="-86" width="170" height="172" />
        <polygon
          className="crea-morph__shape crea-morph__shape--solid"
          points="0,-72 72,68 -72,68"
        />
        <text className="crea-morph__letter" x="0" y="51" textAnchor="middle">A</text>
      </g>
    </svg>
  )
}
