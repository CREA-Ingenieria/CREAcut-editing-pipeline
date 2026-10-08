import { existsSync, lstatSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { copyFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { prepareBackendSetup } from './prepare-backend-setup.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(import.meta.url)
const work = join(root, '.installer-build')
const output = join(root, 'dist', 'windows-release')
const staging = join(work, 'zip')
const config = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
const tar = join(process.env.SystemRoot || 'C:\Windows', 'System32', 'tar.exe')

if (process.platform !== 'win32' || process.arch !== 'x64') {
  throw new Error('Construye el instalador de Windows con Node x64 en Windows.')
}
if (!existsSync(tar)) {
  throw new Error('Se necesita el tar.exe integrado de Windows para crear el .zip.')
}
if (!existsSync(join(root, 'out', 'main', 'index.js'))) {
  throw new Error('Falta out/. Ejecuta primero pnpm run build.')
}

function run(executable, args, cwd = root) {
  const result = spawnSync(executable, args, { cwd, stdio: 'inherit', windowsHide: true })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${executable} termino con codigo ${result.status}`)
}

// Limpia solo estos directorios generados, rechazando enlaces fuera del repo.
for (const directory of [staging, output]) {
  const resolved = existsSync(directory) ? resolve(directory) : resolve(directory)
  if (!resolved.startsWith(root + sep) || (existsSync(directory) && lstatSync(directory).isSymbolicLink())) {
    throw new Error(`Directorio de construccion inseguro: ${directory}`)
  }
  rmSync(directory, { recursive: true, force: true })
  mkdirSync(directory, { recursive: true })
}

await prepareBackendSetup('win32')

const outputRelative = relative(root, output)
if (isAbsolute(outputRelative) || outputRelative.startsWith('..')) throw new Error('Salida fuera del editor.')
console.log('Construyendo el instalador NSIS...')
run(process.execPath, [require.resolve('electron-builder/cli.js'), '--win', 'nsis', '--x64',
  `--config.directories.output=${outputRelative}`, '--publish', 'never'])

const installerName = config.build.win.artifactName.replace('${ext}', 'exe')
const installer = join(output, installerName)
if (!existsSync(installer)) throw new Error(`electron-builder no genero ${installerName}.`)

// El backend se instala desde PyPI, asi que un EXE grande significaria que algo
// pesado se colo dentro: conviene enterarse aqui y no al subir la release.
const installerSize = statSync(installer).size
if (installerSize >= 700 * 1024 * 1024) {
  throw new Error(`El instalador ocupa ${Math.round(installerSize / 1024 / 1024)} MiB; se esperaba una descarga ligera.`)
}

const readmeName = 'LEEME.txt'
writeFileSync(join(staging, readmeName), [
  `CREAcut Beta ${config.version} - Windows x64`,
  '',
  `1. Descomprime este .zip y ejecuta ${installerName}.`,
  '2. Elige la carpeta de instalacion.',
  '3. Espera: el asistente descarga el backend Python, Whisper y Gemma 4.',
  '4. Abre CREAcut Beta y confirma "Backend Python conectado".',
  '',
  'Requiere Windows x64 y conexion a Internet durante la instalacion.',
  'No necesitas instalar Python, Node.js ni preparar un entorno virtual.',
  '',
  'Si tienes una GPU NVIDIA, el asistente te ofrecera el paquete CUDA para',
  'acelerar la transcripcion. Es opcional y ocupa unos 3,7 GB adicionales.',
  ''
].join('\r\n'))
await copyFile(installer, join(staging, installerName))

// Mismo criterio de nombre que el EXE: la release habla de 0.2, no de la
// version tecnica completa.
if (!installerName.includes('-Setup-') || !installerName.endsWith('.exe')) {
  throw new Error(`No se pudo derivar el nombre del .zip de ${installerName}.`)
}
const zipName = `${installerName.replace('-Setup-', '-').slice(0, -'.exe'.length)}-Windows-x64.zip`
console.log('Comprimiendo la entrega...')
run(tar, ['-a', '-c', '-f', join(output, zipName), '-C', staging, installerName, readmeName])

const zipSize = statSync(join(output, zipName)).size
writeFileSync(join(output, 'ARCHIVOS-PARA-PUBLICAR.txt'), `${zipName}\n`)
console.log('')
console.log(`Instalador: ${installerName} (${Math.round(installerSize / 1024 / 1024)} MiB)`)
console.log(`Entrega:    ${zipName} (${Math.round(zipSize / 1024 / 1024)} MiB)`)
console.log(`Carpeta:    ${output}`)
console.log('Publica solo ese .zip. No se ha publicado nada.')
