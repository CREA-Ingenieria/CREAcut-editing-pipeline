import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { CreaMorphLogo } from '../src/renderer/src/components/CreaMorphLogo'

describe('CreaMorphLogo', () => {
  it('representa las cuatro identidades geométricas y las letras CREA', () => {
    const markup = renderToStaticMarkup(<CreaMorphLogo />)

    expect(markup).toContain('Círculo, rombo, rectángulo y triángulo')
    expect(markup.match(/crea-morph__symbol /g)).toHaveLength(4)
    expect(markup).toContain('>C</text>')
    expect(markup).toContain('>R</text>')
    expect(markup).toContain('>E</text>')
    expect(markup).toContain('>A</text>')
    expect(markup).toContain('data-shape="circle"')
    expect(markup).toContain('data-shape="diamond"')
    expect(markup).toContain('data-shape="rectangle"')
    expect(markup).toContain('data-shape="triangle"')
  })

  it('se dibuja como SVG nativo', () => {
    const markup = renderToStaticMarkup(<CreaMorphLogo />)

    expect(markup.startsWith('<svg')).toBe(true)
    expect(markup).not.toContain('<script')
  })
})
