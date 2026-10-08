import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'

interface ResolveBackendRuntimeOptions {
  packaged: boolean
  appRoot: string
  resourcesPath: string
  /** Solo para pruebas: por defecto se toma de LOCALAPPDATA. */
  localAppData?: string
  /** Solo para pruebas: por defecto, el directorio personal del usuario. */
  homeDirectory?: string
  /** Solo para pruebas: por defecto, process.platform. */
  platform?: NodeJS.Platform
}

/** Rutas que usa la pantalla de preparación del primer arranque en macOS. */
export interface BackendSetupPaths {
  uv: string
  manifestPath: string
  runtimeDirectory: string
  backendRoot: string
  logPath: string
}

export interface BackendRuntime {
  appRoot: string
  repoRoot: string
  /** Python del entorno que prepara el instalador (Windows) o el primer arranque (macOS). */
  pythonExecutable?: string
  /** Solo en macOS empaquetado: el entorno se arma en el primer arranque. */
  setup?: BackendSetupPaths
  /** Variables extra para el bridge y los trabajos (solo macOS empaquetado). */
  env?: Record<string, string>
}

/** Carpeta del entorno Python que crea `install-backend.ps1`. */
export function windowsRuntimeDirectory(localAppData: string): string {
  return join(localAppData, 'CREAcut', 'runtime')
}

/** Carpeta del entorno Python que crea la preparación del primer arranque en macOS. */
export function macRuntimeDirectory(homeDirectory: string): string {
  return join(homeDirectory, 'Library', 'Application Support', 'CREAcut', 'runtime')
}

/**
 * Variables que necesita todo Python que corra con el entorno de macOS. Los
 * .pyc se escriben bajo el entorno del usuario y no junto a las fuentes, que
 * viven dentro del .app firmado (y que puede estar en una carpeta sin permiso
 * de escritura).
 */
export function macBackendEnv(runtimeDirectory: string): Record<string, string> {
  return { PYTHONPYCACHEPREFIX: join(runtimeDirectory, 'pycache') }
}

export function resolveBackendRuntime(options: ResolveBackendRuntimeOptions): BackendRuntime {
  if (!options.packaged) {
    return {
      appRoot: options.appRoot,
      repoRoot: resolve(options.appRoot, '..')
    }
  }

  const platform = options.platform ?? process.platform
  const backendRoot = join(options.resourcesPath, 'backend')

  if (platform === 'win32') {
    // En Windows el instalador no incrusta el backend: envía las fuentes y crea
    // el entorno Python desde PyPI. Ese entorno vive fuera de la carpeta de la
    // aplicación para que actualizarla no obligue a descargarlo otra vez.
    const localAppData = options.localAppData ?? process.env.LOCALAPPDATA
    if (!localAppData) {
      throw new Error('Windows no expuso LOCALAPPDATA; no se puede localizar el backend de CREAcut Beta.')
    }
    const pythonExecutable = join(windowsRuntimeDirectory(localAppData), '.venv', 'Scripts', 'python.exe')
    if (!existsSync(pythonExecutable)) {
      throw new Error(
        'El asistente de instalación no dejó preparado el backend Python de CREAcut Beta. ' +
        'Vuelve a ejecutar el instalador para completarlo.'
      )
    }
    return { appRoot: backendRoot, repoRoot: backendRoot, pythonExecutable }
  }

  // macOS lleva las mismas fuentes que Windows, pero no tiene paso de
  // instalador: la pantalla de preparación arma el entorno en el primer
  // arranque. Que el entorno falte aquí no es un error.
  const home = options.homeDirectory ?? homedir()
  const runtimeDirectory = macRuntimeDirectory(home)
  return {
    appRoot: backendRoot,
    repoRoot: backendRoot,
    pythonExecutable: join(runtimeDirectory, '.venv', 'bin', 'python'),
    env: macBackendEnv(runtimeDirectory),
    setup: {
      uv: join(options.resourcesPath, 'backend-setup', 'uv'),
      manifestPath: join(options.resourcesPath, 'backend-setup', 'manifest.json'),
      runtimeDirectory,
      backendRoot,
      logPath: join(home, 'Library', 'Logs', 'CREAcut', 'backend-setup.log')
    }
  }
}
