// Hook afterPack de electron-builder. El DMG de macOS no debe redistribuir
// binarios de terceros con obligaciones de codigo fuente (FFmpeg GPL dentro de
// imageio-ffmpeg y de opencv-python) ni un Python congelado: el entorno se arma
// desde PyPI en el Mac del usuario. Si algo de eso vuelve a colarse en
// Contents/Resources, el empaquetado falla aqui.
import { lstatSync, readdirSync } from 'node:fs'
import { join, relative } from 'node:path'

const FORBIDDEN_FILES = [
  /^ffmpeg(-.*)?(\.exe)?$/i,
  /^lib(avcodec|avformat|avutil|avfilter|avdevice|swresample|swscale|x264|x265)[.-]/i,
  /\.(so|dylib)$/i
]

export function findForbidden(root) {
  const found = []
  const walk = (directory) => {
    for (const entry of readdirSync(directory)) {
      const path = join(directory, entry)
      const stats = lstatSync(path)
      // Un enlace no se sigue (podria salir del paquete), pero su propio nombre
      // cuenta: un ffmpeg o una .dylib enlazados se redistribuyen igual.
      if (stats.isSymbolicLink()) {
        if (entry === 'site-packages' || FORBIDDEN_FILES.some((pattern) => pattern.test(entry))) {
          found.push(relative(root, path))
        }
        continue
      }
      if (stats.isDirectory()) {
        if (entry === 'site-packages') found.push(relative(root, path))
        else walk(path)
        continue
      }
      if (FORBIDDEN_FILES.some((pattern) => pattern.test(entry))) found.push(relative(root, path))
    }
  }
  walk(root)
  return found
}

export default async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return
  const appName = `${context.packager.appInfo.productFilename}.app`
  const resources = join(context.appOutDir, appName, 'Contents', 'Resources')
  const found = findForbidden(resources)
  if (found.length > 0) {
    throw new Error(
      'El paquete de macOS contiene binarios que CREA no debe redistribuir:\n' +
      found.map((path) => `  - ${path}`).join('\n')
    )
  }
  console.log('verify-bundle: Contents/Resources sin FFmpeg ni binarios de Python.')
}
