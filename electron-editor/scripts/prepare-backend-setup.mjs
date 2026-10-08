// Deja en .installer-build/ lo que el instalador necesita para construir el
// backend en la maquina del usuario: el ejecutable uv y el manifiesto con las
// versiones desde las que instalar. Windows lo usa desde NSIS; macOS, desde la
// pantalla de preparacion del primer arranque.
//
// Uso: node scripts/prepare-backend-setup.mjs <win32|darwin>
import { createHash } from 'node:crypto'
import { createWriteStream, existsSync } from 'node:fs'
import { chmod, mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { pipeline } from 'node:stream/promises'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = join(root, '.installer-build')
const cache = join(work, 'cache')

// PyTorch publica las ruedas CPU y CUDA en indices separados. cu128 corresponde
// a las bibliotecas CUDA 12.8 que traia el backend congelado anterior. En macOS
// se usa el indice estandar de PyPI: no hay CUDA y la rueda ya incluye MPS.
const UV_VERSION = process.env.CREACUT_UV_VERSION || '0.9.30'
const PYTHON_VERSION = '3.12'
const CPU_INDEX = 'https://download.pytorch.org/whl/cpu'
const CUDA_INDEX = 'https://download.pytorch.org/whl/cu128'

export function uvTarget(platform) {
  if (platform === 'win32') {
    return { archive: 'uv-x86_64-pc-windows-msvc.zip', binary: 'uv.exe', member: 'uv.exe', stripComponents: 0 }
  }
  if (platform === 'darwin') {
    // Solo Apple Silicon. El .tar.gz trae uv dentro de una carpeta con el nombre del objetivo.
    return {
      archive: 'uv-aarch64-apple-darwin.tar.gz',
      binary: 'uv',
      member: 'uv-aarch64-apple-darwin/uv',
      stripComponents: 1
    }
  }
  throw new Error(`No hay instalador de CREAcut para la plataforma ${platform}.`)
}

export function backendManifest(platform, version) {
  const manifest = { version, pythonVersion: PYTHON_VERSION }
  if (platform === 'win32') Object.assign(manifest, { cpuIndex: CPU_INDEX, cudaIndex: CUDA_INDEX })
  return manifest
}

async function download(url, destination) {
  const response = await fetch(url, { redirect: 'follow' })
  if (!response.ok) throw new Error(`No se pudo descargar ${url}: HTTP ${response.status}`)
  await mkdir(dirname(destination), { recursive: true })
  await pipeline(response.body, createWriteStream(destination))
}

async function sha256(path) {
  const digest = createHash('sha256')
  digest.update(await readFile(path))
  return digest.digest('hex')
}

async function fetchUv(platform) {
  const target = uvTarget(platform)
  const uv = join(work, target.binary)
  const base = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${target.archive}`
  const archive = join(cache, `${UV_VERSION}-${target.archive}`)

  if (!existsSync(archive)) {
    console.log(`Descargando uv ${UV_VERSION} (${target.archive})...`)
    await download(base, archive)
    // El .sha256 vive en la misma release, asi que no es una garantia frente a
    // un origen comprometido; sirve para detectar una descarga corrupta.
    try {
      const expected = join(cache, `${UV_VERSION}-${target.archive}.sha256`)
      await download(`${base}.sha256`, expected)
      const declared = (await readFile(expected, 'utf8')).trim().split(/\s+/)[0]
      const actual = await sha256(archive)
      if (declared.length === 64 && declared.toLowerCase() !== actual) {
        await rm(archive, { force: true })
        throw new Error('La descarga de uv no coincide con su SHA-256 publicado.')
      }
    } catch (error) {
      if (error.message.includes('SHA-256')) throw error
      console.warn(`Aviso: no se pudo comprobar el SHA-256 de uv (${error.message}).`)
    }
  }

  // Windows usa su tar.exe integrado (lee .zip); macOS, el tar del sistema.
  const tar = platform === 'win32'
    ? join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe')
    : 'tar'
  if (platform === 'win32' && !existsSync(tar)) {
    throw new Error('Se necesita el tar.exe integrado de Windows para extraer uv.')
  }
  await rm(uv, { force: true })
  const args = ['-x', '-f', archive, '-C', work]
  if (target.stripComponents) args.push(`--strip-components=${target.stripComponents}`)
  args.push(target.member)
  const extracted = spawnSync(tar, args, { stdio: 'inherit', windowsHide: true })
  if (extracted.error) throw extracted.error
  if (extracted.status !== 0) throw new Error(`No se pudo extraer ${target.binary} del archivo descargado.`)
  if (!existsSync(uv)) throw new Error(`El archivo de uv no contenia ${target.binary}.`)
  await chmod(uv, 0o755)
  const { size } = await stat(uv)
  console.log(`uv ${UV_VERSION} listo (${Math.round(size / 1024 / 1024)} MiB).`)
  return uv
}

export async function prepareBackendSetup(platform = process.platform) {
  const config = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'))
  await mkdir(cache, { recursive: true })
  await fetchUv(platform)
  await writeFile(join(work, 'manifest.json'), `${JSON.stringify(backendManifest(platform, config.version), null, 2)}\n`)
  console.log(`Manifiesto del backend (${platform}) escrito para la version ${config.version}.`)
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  await prepareBackendSetup(process.argv[2] || process.platform)
}
