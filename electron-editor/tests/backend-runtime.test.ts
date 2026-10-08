import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { macRuntimeDirectory, resolveBackendRuntime } from '../src/main/backend-runtime'

describe('resolveBackendRuntime', () => {
  it('en macOS empaquetado no exige el entorno y devuelve las rutas de preparación', () => {
    const runtime = resolveBackendRuntime({
      packaged: true,
      appRoot: '/Applications/CREAcut Beta.app/Contents/Resources/app.asar',
      resourcesPath: '/R',
      platform: 'darwin',
      homeDirectory: '/Users/ana'
    })
    const runtimeDirectory = join('/Users/ana', 'Library', 'Application Support', 'CREAcut', 'runtime')

    expect(macRuntimeDirectory('/Users/ana')).toBe(runtimeDirectory)
    expect(runtime.appRoot).toBe(join('/R', 'backend'))
    expect(runtime.repoRoot).toBe(join('/R', 'backend'))
    expect(runtime.pythonExecutable).toBe(join(runtimeDirectory, '.venv', 'bin', 'python'))
    expect(runtime.setup).toEqual({
      uv: join('/R', 'backend-setup', 'uv'),
      manifestPath: join('/R', 'backend-setup', 'manifest.json'),
      runtimeDirectory,
      backendRoot: join('/R', 'backend'),
      logPath: join('/Users/ana', 'Library', 'Logs', 'CREAcut', 'backend-setup.log')
    })
    // Los .pyc van al entorno del usuario: el .app firmado no se toca.
    expect(runtime.env).toEqual({ PYTHONPYCACHEPREFIX: join(runtimeDirectory, 'pycache') })
  })

  it('en desarrollo no hay preparación en ninguna plataforma', () => {
    for (const platform of ['darwin', 'win32'] as const) {
      const runtime = resolveBackendRuntime({ packaged: false, appRoot: '/repo/electron-editor', resourcesPath: '/R', platform })
      expect(runtime.setup).toBeUndefined()
      expect(runtime.env).toBeUndefined()
      expect(runtime.repoRoot).toBe(resolve('/repo/electron-editor', '..'))
    }
  })

  it('en Windows empaquetado sigue exigiendo el entorno del instalador', () => {
    expect(() => resolveBackendRuntime({
      packaged: true, appRoot: '/a', resourcesPath: '/R', platform: 'win32', localAppData: join('/no', 'existe')
    })).toThrow(/asistente de instalación/)
  })

  it('en Windows empaquetado no añade variables al entorno del backend', () => {
    const localAppData = mkdtempSync(join(tmpdir(), 'creacut-lad-'))
    const scripts = join(localAppData, 'CREAcut', 'runtime', '.venv', 'Scripts')
    mkdirSync(scripts, { recursive: true })
    writeFileSync(join(scripts, 'python.exe'), '')
    const runtime = resolveBackendRuntime({ packaged: true, appRoot: '/a', resourcesPath: '/R', platform: 'win32', localAppData })
    expect(runtime.pythonExecutable).toBe(join(scripts, 'python.exe'))
    expect(runtime.env).toBeUndefined()
  })
})
