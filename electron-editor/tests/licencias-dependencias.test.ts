import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * CREAcut se distribuye bajo la GPL-3.0-or-later, así que todo lo que viaja
 * dentro del editor tiene que poder redistribuirse con ella. La prueba lee la
 * licencia que declara cada dependencia de ejecución instalada y falla si no
 * está en la lista. Agregar una licencia aquí exige comprobar antes que es
 * compatible con la GPL-3.0. OFL-1.1 cubre solo fuentes tipográficas.
 */
const GPL_COMPATIBLE = new Set(['MIT', 'ISC', 'BSD-2-Clause', 'BSD-3-Clause', 'Apache-2.0', '0BSD', 'OFL-1.1'])

const root = fileURLToPath(new URL('..', import.meta.url))
const readJson = (path: string): Record<string, unknown> => JSON.parse(readFileSync(path, 'utf8'))
const manifest = readJson(`${root}package.json`) as { dependencies?: Record<string, string> }

function declaredLicense(name: string): string {
  const { license } = readJson(`${root}node_modules/${name}/package.json`)
  return typeof license === 'string' ? license : JSON.stringify(license)
}

describe('licencias de las dependencias del editor', () => {
  it.each(Object.keys(manifest.dependencies ?? {}))('%s es compatible con la GPL-3.0', (name) => {
    const license = declaredLicense(name)
    expect(GPL_COMPATIBLE.has(license), `${name} declara ${license}`).toBe(true)
  })
})
