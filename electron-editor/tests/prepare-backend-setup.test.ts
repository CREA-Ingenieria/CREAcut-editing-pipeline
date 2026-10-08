import { describe, expect, it } from 'vitest'
// @ts-expect-error: módulo .mjs sin tipos
import { backendManifest, uvTarget } from '../scripts/prepare-backend-setup.mjs'

describe('prepare-backend-setup', () => {
  it('elige el uv de Apple Silicon y lo extrae de su carpeta', () => {
    expect(uvTarget('darwin')).toEqual({
      archive: 'uv-aarch64-apple-darwin.tar.gz',
      binary: 'uv',
      member: 'uv-aarch64-apple-darwin/uv',
      stripComponents: 1
    })
  })

  it('conserva el uv de Windows', () => {
    expect(uvTarget('win32')).toEqual({
      archive: 'uv-x86_64-pc-windows-msvc.zip',
      binary: 'uv.exe',
      member: 'uv.exe',
      stripComponents: 0
    })
  })

  it('el manifiesto de macOS no lleva índices de PyTorch', () => {
    expect(backendManifest('darwin', '0.2.0-beta.1')).toEqual({ version: '0.2.0-beta.1', pythonVersion: '3.12' })
  })

  it('el manifiesto de Windows conserva los índices CPU y CUDA', () => {
    expect(backendManifest('win32', '0.2.0-beta.1')).toEqual({
      version: '0.2.0-beta.1',
      pythonVersion: '3.12',
      cpuIndex: 'https://download.pytorch.org/whl/cpu',
      cudaIndex: 'https://download.pytorch.org/whl/cu128'
    })
  })

  it('rechaza plataformas sin instalador', () => {
    expect(() => uvTarget('linux')).toThrow(/linux/)
  })
})
