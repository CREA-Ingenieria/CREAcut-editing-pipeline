import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { createInterface } from 'node:readline'

interface PendingRequest {
  resolve: (value: unknown) => void
  reject: (error: Error) => void
  timer: NodeJS.Timeout
}

interface BridgeEnvelope {
  id: number
  ok: boolean
  result?: unknown
  error?: {
    type?: string
    message?: string
    detail?: string
  }
}

export class PythonBridge {
  private process: ChildProcessWithoutNullStreams | null = null
  private nextId = 1
  private pending = new Map<number, PendingRequest>()
  private stderrTail: string[] = []

  constructor(
    private readonly appRoot: string,
    private readonly repoRoot: string,
    private readonly installedPython?: string,
    /** Variables propias de la plataforma (p. ej. PYTHONPYCACHEPREFIX en macOS). */
    private readonly extraEnv: Record<string, string> = {}
  ) {}

  pythonExecutable(): string {
    const configured = process.env.CREACUT_PYTHON?.trim()
    if (configured) return configured

    // Empaquetado: el entorno que preparó el instalador (Windows) o el primer arranque (macOS).
    if (this.installedPython && existsSync(this.installedPython)) return this.installedPython

    const windowsVenv = join(this.repoRoot, '.venv', 'Scripts', 'python.exe')
    if (existsSync(windowsVenv)) return windowsVenv

    const unixVenv = join(this.repoRoot, '.venv', 'bin', 'python')
    if (existsSync(unixVenv)) return unixVenv

    return process.platform === 'win32' ? 'python' : 'python3'
  }

  private ensureStarted(): ChildProcessWithoutNullStreams {
    if (this.process && !this.process.killed) return this.process

    const bridgePath = join(this.appRoot, 'python', 'bridge.py')
    const executable = this.pythonExecutable()
    const args = ['-u', bridgePath, '--repo-root', this.repoRoot]
    const child = spawn(
      executable,
      args,
      {
        cwd: this.repoRoot,
        env: {
          ...process.env,
          ...this.extraEnv,
          PYTHONUTF8: '1',
          PYTHONUNBUFFERED: '1'
        },
        windowsHide: true
      }
    )

    this.process = child
    this.stderrTail = []

    const lines = createInterface({ input: child.stdout })
    lines.on('line', (line) => this.handleLine(line))

    child.stderr.setEncoding('utf8')
    child.stderr.on('data', (chunk: string) => {
      this.stderrTail.push(chunk.trim())
      this.stderrTail = this.stderrTail.slice(-12)
    })

    child.on('error', (error) => this.failAll(error))
    child.on('exit', (code, signal) => {
      const detail = this.stderrTail.filter(Boolean).join('\n')
      const reason = `El backend Python terminó (código ${code ?? '—'}, señal ${signal ?? '—'}).${detail ? `\n${detail}` : ''}`
      this.process = null
      this.failAll(new Error(reason))
    })

    return child
  }

  private handleLine(line: string): void {
    let response: BridgeEnvelope
    try {
      response = JSON.parse(line) as BridgeEnvelope
    } catch {
      this.stderrTail.push(`Respuesta no válida: ${line}`)
      return
    }

    const request = this.pending.get(response.id)
    if (!request) return
    clearTimeout(request.timer)
    this.pending.delete(response.id)

    if (response.ok) {
      request.resolve(response.result)
      return
    }

    const message = response.error?.message || 'El backend Python devolvió un error'
    const detail = response.error?.detail
    request.reject(new Error(detail ? `${message}\n${detail}` : message))
  }

  private failAll(error: Error): void {
    for (const request of this.pending.values()) {
      clearTimeout(request.timer)
      request.reject(error)
    }
    this.pending.clear()
  }

  request<T>(method: string, params: Record<string, unknown> = {}, timeoutMs = 120_000): Promise<T> {
    const child = this.ensureStarted()
    const id = this.nextId++

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`La operación ${method} superó el tiempo máximo de espera`))
      }, timeoutMs)

      this.pending.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
        timer
      })

      child.stdin.write(`${JSON.stringify({ id, method, params })}\n`, (error) => {
        if (!error) return
        clearTimeout(timer)
        this.pending.delete(id)
        reject(error)
      })
    })
  }

  close(): void {
    if (!this.process || this.process.killed) return
    this.process.stdin.end()
    this.process.kill()
    this.process = null
  }
}
