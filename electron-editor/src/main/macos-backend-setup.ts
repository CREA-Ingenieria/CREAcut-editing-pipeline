import { spawn, type ChildProcess } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { createInterface } from 'node:readline'
import { macBackendEnv, type BackendSetupPaths } from './backend-runtime'
import {
  applySetupProgress,
  initialSetupSteps,
  parseWhisperPercent,
  type BackendSetupErrorKind,
  type BackendSetupProgress,
  type BackendSetupStatus,
  type BackendSetupStepId
} from '../shared/backend-setup'

/**
 * Preparación del primer arranque en macOS.
 *
 * El DMG no lleva un Python congelado: igual que el instalador de Windows
 * (`install-backend.ps1`), arma un entorno desde PyPI con uv en el Mac del
 * usuario. Así CREA no redistribuye binarios de terceros con obligaciones de
 * código fuente, como el FFmpeg GPL de imageio-ffmpeg y de opencv-python.
 */
export interface RunOptions {
  env: NodeJS.ProcessEnv
  onLine: (line: string) => void
  /** Al cancelarse, el comando (y lo que haya lanzado) se mata y la promesa rechaza. */
  signal?: AbortSignal
  /** Pasado este tiempo, el comando se mata y la promesa rechaza (código ETIMEDOUT). */
  timeoutMs?: number
}

export interface CommandRunner {
  run(executable: string, args: string[], options: RunOptions): Promise<number>
}

export interface SetupManifest {
  version: string
  pythonVersion: string
}

export class SetupStepError extends Error {
  constructor(
    readonly stepId: BackendSetupStepId,
    message: string,
    readonly detail: string,
    /** `launch` si el comando ni siquiera se pudo ejecutar; `step` si corrió y falló. */
    readonly kind: Extract<BackendSetupErrorKind, 'launch' | 'step'> = 'step'
  ) {
    super(message)
    this.name = 'SetupStepError'
  }
}

/** Errores de spawn que en un Mac suelen venir de Gatekeeper o de la cuarentena, no de la red. */
const LAUNCH_ERROR_CODES = new Set(['EACCES', 'ENOENT', 'EPERM'])

function isLaunchError(error: unknown): boolean {
  return typeof error === 'object' && error !== null &&
    LAUNCH_ERROR_CODES.has(String((error as { code?: unknown }).code))
}

/** La preparación se interrumpió (la app se está cerrando). */
export class SetupCancelledError extends Error {
  constructor() {
    super('Se interrumpió la preparación.')
    this.name = 'SetupCancelledError'
  }
}

const DETAIL_LINES = 40
/** La verificación de cada arranque importa torch y compañía: en un disco lento tarda, pero no 2 minutos. */
export const VERIFY_TIMEOUT_MS = 120_000

/** Escritor del registro de la preparación. Es de ayuda: si falla, no frena nada. */
function logWriter(logPath: string): (line: string) => void {
  let directoryReady = false
  return (line) => {
    try {
      if (!directoryReady) {
        mkdirSync(dirname(logPath), { recursive: true })
        directoryReady = true
      }
      appendFileSync(logPath, `${line}\n`)
    } catch {
      // Registro best-effort.
    }
  }
}

export function venvPython(runtimeDirectory: string): string {
  return join(runtimeDirectory, '.venv', 'bin', 'python')
}

export function markerPath(runtimeDirectory: string): string {
  return join(runtimeDirectory, 'backend.json')
}

export function readManifest(path: string): SetupManifest {
  const manifest = JSON.parse(readFileSync(path, 'utf8')) as Partial<SetupManifest>
  if (typeof manifest.version !== 'string' || !/^3\.\d+$/.test(manifest.pythonVersion ?? '')) {
    throw new Error(`Manifiesto del backend inválido: ${path}`)
  }
  return { version: manifest.version, pythonVersion: manifest.pythonVersion as string }
}

export function setupEnvironment(paths: BackendSetupPaths): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ...macBackendEnv(paths.runtimeDirectory),
    // Ni uv.toml ni pyproject del usuario: la preparación siempre es la misma.
    UV_NO_CONFIG: '1',
    // CPython gestionado por uv junto al entorno: no depende del Python del usuario.
    UV_PYTHON_INSTALL_DIR: join(paths.runtimeDirectory, 'python'),
    // Las barras de progreso de uv son secuencias ANSI; interesan las líneas de resumen.
    UV_NO_PROGRESS: '1',
    UV_HTTP_TIMEOUT: '180',
    PYTHONUTF8: '1',
    PYTHONUNBUFFERED: '1'
  }
  // Un Python o un entorno virtual del usuario no puede colarse en el de CREAcut.
  delete env.PYTHONPATH
  delete env.PYTHONHOME
  delete env.VIRTUAL_ENV
  return env
}

export async function checkEnvironment(
  paths: BackendSetupPaths,
  runner: CommandRunner,
  signal?: AbortSignal
): Promise<'ready' | 'needs-setup'> {
  const python = venvPython(paths.runtimeDirectory)
  const marker = markerPath(paths.runtimeDirectory)
  if (!existsSync(marker) || !existsSync(python)) return 'needs-setup'
  try {
    const installed = JSON.parse(readFileSync(marker, 'utf8')) as { version?: unknown }
    if (installed.version !== readManifest(paths.manifestPath).version) return 'needs-setup'
  } catch {
    return 'needs-setup'
  }
  // Mismo criterio que install-backend.ps1: que el marcador exista no basta,
  // el entorno tiene que poder importar lo que usa el backend.
  // Corre en cada arranque: su salida queda en el registro y tiene tiempo máximo,
  // porque mientras tanto la persona solo ve «Abriendo CREAcut…».
  const verify = join(paths.backendRoot, 'python', 'verify_backend.py')
  const log = logWriter(paths.logPath)
  log(`== verify · ${new Date().toISOString()}`)
  try {
    const code = await runner.run(python, [verify], {
      env: setupEnvironment(paths),
      onLine: log,
      signal,
      timeoutMs: VERIFY_TIMEOUT_MS
    })
    log(code === 0 ? '== verify: listo' : `== verify: falló (código ${code}); hay que preparar el entorno`)
    return code === 0 ? 'ready' : 'needs-setup'
  } catch (error) {
    log(`== verify: ${error instanceof Error ? error.message : String(error)}`)
    return 'needs-setup'
  }
}

interface SetupCommand {
  id: BackendSetupStepId
  executable: string
  args: string[]
  failure: string
}

export async function runSetup(
  paths: BackendSetupPaths,
  runner: CommandRunner,
  onProgress: (event: BackendSetupProgress) => void,
  signal?: AbortSignal
): Promise<void> {
  if (signal?.aborted) throw new SetupCancelledError()
  const manifest = readManifest(paths.manifestPath)
  const venv = join(paths.runtimeDirectory, '.venv')
  const python = venvPython(paths.runtimeDirectory)
  const backendPython = join(paths.backendRoot, 'python')
  const env = setupEnvironment(paths)

  mkdirSync(paths.runtimeDirectory, { recursive: true })
  // Sin marcador hasta el final: si la app se cierra a mitad de camino, el
  // siguiente arranque reconstruye el entorno en vez de usar uno incompleto.
  rmSync(markerPath(paths.runtimeDirectory), { force: true })
  rmSync(venv, { recursive: true, force: true })

  const log = logWriter(paths.logPath)
  log(`== Preparación de CREAcut ${manifest.version} · ${new Date().toISOString()}`)

  const commands: SetupCommand[] = [
    {
      id: 'python',
      executable: paths.uv,
      args: ['venv', venv, '--python', manifest.pythonVersion, '--python-preference', 'only-managed'],
      failure: `No se pudo preparar Python ${manifest.pythonVersion}.`
    },
    {
      id: 'torch',
      executable: paths.uv,
      args: ['pip', 'install', '--python', python, 'torch'],
      failure: 'No se pudo instalar PyTorch.'
    },
    {
      id: 'dependencies',
      executable: paths.uv,
      args: ['pip', 'install', '--python', python, '-r', join(backendPython, 'requirements-runtime.txt')],
      failure: 'No se pudieron instalar las dependencias.'
    },
    {
      id: 'verify',
      executable: python,
      args: [join(backendPython, 'verify_backend.py')],
      failure: 'El entorno quedó incompleto: alguna dependencia no se puede importar.'
    },
    {
      id: 'whisper',
      executable: python,
      args: [join(backendPython, 'setup_models.py'), '--solo-whisper'],
      failure: 'No se pudo descargar Whisper.'
    }
  ]

  const tail: string[] = []
  const remember = (line: string): void => {
    log(line)
    tail.push(line)
    if (tail.length > DETAIL_LINES) tail.shift()
  }

  const cancelled = (): SetupCancelledError => {
    log('== Preparación interrumpida')
    return new SetupCancelledError()
  }

  for (const command of commands) {
    if (signal?.aborted) throw cancelled()
    onProgress({ stepId: command.id, state: 'running' })
    log(`== ${command.id}: ${[command.executable, ...command.args].join(' ')}`)
    let code: number
    let launchFailed = false
    try {
      code = await runner.run(command.executable, command.args, {
        env,
        onLine: (line) => {
          remember(line)
          const percent = command.id === 'whisper' ? parseWhisperPercent(line) : undefined
          onProgress({ stepId: command.id, state: 'running', message: line, percent })
        },
        signal
      })
    } catch (error) {
      if (signal?.aborted) throw cancelled()
      remember(error instanceof Error ? error.message : String(error))
      launchFailed = isLaunchError(error)
      code = -1
    }
    // Un comando que termina justo al cancelar no autoriza el paso siguiente.
    if (signal?.aborted) throw cancelled()
    if (code !== 0) {
      const failure = !launchFailed ? command.failure : command.executable === paths.uv
        ? 'No se pudo ejecutar uv, el instalador de Python que viene con CREAcut.'
        : 'No se pudo ejecutar Python del entorno.'
      onProgress({ stepId: command.id, state: 'failed', message: failure })
      log(`== ${command.id} falló (código ${code})`)
      throw new SetupStepError(command.id, failure, tail.join('\n'), launchFailed ? 'launch' : 'step')
    }
    onProgress({ stepId: command.id, state: 'done' })
  }

  writeFileSync(markerPath(paths.runtimeDirectory), `${JSON.stringify({
    version: manifest.version,
    pythonVersion: manifest.pythonVersion,
    installedAt: new Date().toISOString()
  }, null, 2)}\n`)
  log('== Preparación completa')
}

/**
 * Mata el comando y todo lo que haya lanzado. En macOS cada comando es líder
 * de su propio grupo de procesos (`detached`), así que `kill(-pid)` alcanza
 * también a los hijos de uv. Windows no tiene grupos POSIX: ahí (solo pruebas
 * y desarrollo, la preparación es exclusiva de macOS) basta con el proceso.
 */
function killTree(child: ChildProcess): void {
  if (process.platform !== 'win32' && child.pid !== undefined) {
    try {
      process.kill(-child.pid, 'SIGKILL')
      return
    } catch {
      // El grupo ya no existe: se intenta con el proceso directamente.
    }
  }
  child.kill('SIGKILL')
}

export const spawnRunner: CommandRunner = {
  run(executable, args, { env, onLine, signal, timeoutMs }) {
    return new Promise((resolvePromise, reject) => {
      if (signal?.aborted) {
        reject(new SetupCancelledError())
        return
      }
      // stdin cerrado: ningún comando de la preparación debe quedarse esperando entrada.
      const child = spawn(executable, args, {
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: process.platform !== 'win32'
      })
      let settled = false
      let timer: NodeJS.Timeout | undefined
      const settle = (finish: () => void): void => {
        if (settled) return
        settled = true
        if (timer) clearTimeout(timer)
        signal?.removeEventListener('abort', onAbort)
        finish()
      }
      // Rechaza en el acto: al salir de la app no hay tiempo de esperar el cierre.
      const onAbort = (): void => {
        killTree(child)
        settle(() => reject(new SetupCancelledError()))
      }
      signal?.addEventListener('abort', onAbort)
      if (timeoutMs !== undefined) {
        timer = setTimeout(() => {
          killTree(child)
          const error = Object.assign(
            new Error(`El comando superó el tiempo máximo (${timeoutMs / 1000} s).`),
            { code: 'ETIMEDOUT' }
          )
          settle(() => reject(error))
        }, timeoutMs)
      }
      // Un fallo dentro de onLine (disco lleno, ventana destruida) no puede
      // escapar del listener como excepción no capturada: se guarda y se rechaza al cerrar.
      let callbackError: unknown
      const forward = (stream: NodeJS.ReadableStream): void => {
        createInterface({ input: stream }).on('line', (line) => {
          const trimmed = line.trim()
          // Tras cancelar o vencer el tiempo, lo que quede en el búfer ya no interesa.
          if (!trimmed || settled) return
          try {
            onLine(trimmed)
          } catch (error) {
            callbackError ??= error
          }
        })
      }
      forward(child.stdout)
      forward(child.stderr)
      child.on('error', (error) => settle(() => reject(error)))
      child.on('close', (code) => settle(() => {
        if (callbackError !== undefined) reject(callbackError)
        else resolvePromise(code ?? -1)
      }))
    })
  }
}

/**
 * Mantiene el estado que ve la pantalla de preparación y garantiza una sola
 * preparación a la vez. `onReady` se llama una única vez, cuando el entorno
 * queda listo (ya existía o se acaba de preparar).
 */
export class BackendSetupController {
  private current: BackendSetupStatus
  private running: Promise<BackendSetupStatus> | null = null
  private checking: Promise<'ready' | 'needs-setup'> | null = null
  private readyNotified = false
  // Una sola señal para toda la vida del controlador: cancelar es solo para la salida de la app.
  private readonly abort = new AbortController()

  constructor(
    private readonly paths: BackendSetupPaths,
    private readonly runner: CommandRunner,
    private readonly emit: (status: BackendSetupStatus) => void,
    private readonly onReady: () => void
  ) {
    this.current = { state: 'needs-setup', steps: initialSetupSteps(), logPath: paths.logPath }
  }

  async status(): Promise<BackendSetupStatus> {
    if (this.running || this.current.state === 'ready' || this.current.state === 'failed') return this.current
    // Llamadas simultáneas (p. ej. StrictMode) comparten una sola verificación.
    this.checking ??= checkEnvironment(this.paths, this.runner, this.abort.signal).finally(() => { this.checking = null })
    const result = await this.checking
    // Si start() arrancó mientras se verificaba, el .venv se está reconstruyendo, y
    // si ya terminó (p. ej. con un fallo rápido), su resultado manda: solo se marca
    // listo si nada cambió el estado durante la verificación.
    if (result === 'ready' && !this.running && this.current.state === 'needs-setup') this.markReady()
    return this.current
  }

  /** Mata el comando en curso (al salir de la app); la preparación queda sin marcador. */
  cancel(): void {
    this.abort.abort()
  }

  start(): Promise<BackendSetupStatus> {
    if (this.current.state === 'ready') return Promise.resolve(this.current)
    if (this.running) return this.running
    this.current = { state: 'running', steps: initialSetupSteps(), logPath: this.paths.logPath }
    this.emit(this.current)
    this.running = runSetup(this.paths, this.runner, (event) => {
      this.current = applySetupProgress(this.current, event)
      // El fallo se emite una sola vez, completo, desde el catch.
      if (event.state !== 'failed') this.emit(this.current)
    }, this.abort.signal)
      .then(() => this.markReady())
      .catch((error: unknown) => {
        const step = error instanceof SetupStepError ? error : null
        this.current = {
          ...this.current,
          state: 'failed',
          error: step ? step.message
            : error instanceof SetupCancelledError ? error.message
              : 'No se pudo iniciar la preparación.',
          errorKind: step ? step.kind : 'start',
          detail: step ? step.detail : (error instanceof Error ? error.message : String(error))
        }
        this.emit(this.current)
      })
      .then(() => {
        this.running = null
        return this.current
      })
    return this.running
  }

  private markReady(): void {
    this.current = { ...this.current, state: 'ready', error: undefined, errorKind: undefined, detail: undefined }
    this.emit(this.current)
    if (!this.readyNotified) {
      this.readyNotified = true
      this.onReady()
    }
  }
}
