import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

interface Resource { from: string; to: string }
const pkg = JSON.parse(readFileSync(join(__dirname, '..', 'package.json'), 'utf8'))
const mac: Resource[] = pkg.build.mac.extraResources

describe('configuración del DMG', () => {
  it('lleva las fuentes del backend y uv, no el backend congelado', () => {
    const pairs = mac.map((entry) => `${entry.from} -> ${entry.to}`)
    expect(pairs).toEqual(expect.arrayContaining([
      'python -> backend/python',
      '../creacut -> backend/creacut',
      '../assets -> backend/assets',
      '.installer-build/uv -> backend-setup/uv',
      '.installer-build/manifest.json -> backend-setup/manifest.json'
    ]))
    expect(mac.some((entry) => entry.from.includes('backend-runtime'))).toBe(false)
  })

  it('verifica el paquete después de empaquetar', () => {
    expect(pkg.build.afterPack).toBe('scripts/verify-bundle.mjs')
  })

  it('los scripts de macOS ya no congelan el backend', () => {
    expect(pkg.scripts['prepare:backend']).toBeUndefined()
    expect(pkg.scripts['prepare:mac-setup']).toBe('node scripts/prepare-backend-setup.mjs darwin')
    expect(pkg.scripts['prepare:win-setup']).toBe('node scripts/prepare-backend-setup.mjs win32')
    for (const name of ['pack:mac', 'dist:mac']) {
      expect(pkg.scripts[name]).toContain('pnpm run prepare:mac-setup')
      expect(pkg.scripts[name]).not.toContain('prepare:backend')
    }
  })

  it('el DMG se construye solo para Apple Silicon', () => {
    for (const name of ['pack:mac', 'dist:mac']) {
      expect(pkg.scripts[name]).toMatch(/electron-builder --mac .*--arm64/)
    }
  })
})
