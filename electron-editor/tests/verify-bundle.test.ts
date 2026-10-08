import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
// @ts-expect-error: módulo .mjs sin tipos
import { findForbidden } from '../scripts/verify-bundle.mjs'

function tree(files: string[]): string {
  const root = mkdtempSync(join(tmpdir(), 'creacut-bundle-'))
  for (const file of files) {
    mkdirSync(join(root, file, '..'), { recursive: true })
    writeFileSync(join(root, file), '')
  }
  return root
}

// Windows sin modo desarrollador no deja crear enlaces simbólicos sin permisos de administrador.
function canSymlink(): boolean {
  const root = mkdtempSync(join(tmpdir(), 'creacut-link-'))
  try {
    writeFileSync(join(root, 'destino'), '')
    symlinkSync(join(root, 'destino'), join(root, 'enlace'), 'file')
    return true
  } catch {
    return false
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
}

describe('verify-bundle', () => {
  it('acepta un Resources limpio', () => {
    const root = tree([
      'app.asar',
      'icon.png',
      'backend/python/bridge.py',
      'backend/python/requirements-runtime.txt',
      'backend/creacut/transcribe.py',
      'backend/assets/fonts/Inter-Variable.ttf',
      'backend-setup/uv',
      'backend-setup/manifest.json'
    ])
    expect(findForbidden(root)).toEqual([])
  })

  it('detecta FFmpeg, libav, librerías nativas y site-packages', () => {
    const root = tree([
      'backend-runtime/creacut-backend/ffmpeg',
      'x/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1',
      'x/cv2/.dylibs/libavcodec.61.19.101.dylib',
      'x/libx264.164.dylib',
      'x/_core.cpython-312-darwin.so',
      'lib/python3.12/site-packages/numpy/__init__.py'
    ])
    const found = findForbidden(root).map((path: string) => path.replaceAll('\\', '/')).sort()
    expect(found).toEqual([
      'backend-runtime/creacut-backend/ffmpeg',
      'lib/python3.12/site-packages',
      'x/_core.cpython-312-darwin.so',
      'x/cv2/.dylibs/libavcodec.61.19.101.dylib',
      'x/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1',
      'x/libx264.164.dylib'
    ])
  })

  // Las uniones (junction) de Windows no piden permisos y Node las ve como enlaces simbólicos.
  it.runIf(process.platform === 'win32')('en Windows, un enlace de carpeta con nombre prohibido también cuenta', () => {
    const outside = tree(['bin/x'])
    const root = tree(['backend-setup/uv'])
    symlinkSync(join(outside, 'bin'), join(root, 'backend-setup', 'ffmpeg'), 'junction')
    symlinkSync(join(outside, 'bin'), join(root, 'site-packages'), 'junction')
    symlinkSync(join(outside, 'bin'), join(root, 'herramientas'), 'junction')
    const found = findForbidden(root).map((path: string) => path.replaceAll('\\', '/')).sort()
    expect(found).toEqual(['backend-setup/ffmpeg', 'site-packages'])
  })

  it.skipIf(!canSymlink())(
    'detecta un FFmpeg o una librería que llegan como enlace simbólico, sin seguirlos (se omite si el sistema no deja crear enlaces simbólicos)',
    () => {
      const outside = tree(['herramienta'])
      const root = tree(['backend-setup/uv'])
      symlinkSync(join(outside, 'herramienta'), join(root, 'backend-setup', 'ffmpeg'), 'file')
      symlinkSync(join(outside, 'herramienta'), join(root, 'backend-setup', 'libavcodec.61.dylib'), 'file')
      symlinkSync(join(outside, 'herramienta'), join(root, 'backend-setup', 'inocente'), 'file')
      const found = findForbidden(root).map((path: string) => path.replaceAll('\\', '/')).sort()
      expect(found).toEqual(['backend-setup/ffmpeg', 'backend-setup/libavcodec.61.dylib'])
    }
  )
})
