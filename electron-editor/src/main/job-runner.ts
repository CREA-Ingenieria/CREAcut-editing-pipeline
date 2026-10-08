import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { join } from 'node:path'
import { createInterface } from 'node:readline'
import { randomUUID } from 'node:crypto'

export type JobKind = 'analysis' | 'render' | 'batch'

export interface JobEvent {
  jobId: string
  jobKind: JobKind
  kind: 'started' | 'progress' | 'device' | 'completed' | 'failed' | 'cancelled'
  message?: string
  device?: string
  label?: string
  result?: Record<string, unknown>
  error?: string
  detail?: string
  itemIndex?: number
  itemTotal?: number
}

interface ActiveJob {
  id: string
  kind: JobKind
  process: ChildProcessWithoutNullStreams
  terminalEventSeen: boolean
}

export class JobRunner {
  private active: ActiveJob | null = null

  constructor(
    private readonly pythonExecutable: string,
    private readonly appRoot: string,
    private readonly repoRoot: string,
    private readonly report: (event: JobEvent) => void,
    /** Variables propias de la plataforma (p. ej. PYTHONPYCACHEPREFIX en macOS). */
    private readonly extraEnv: Record<string, string> = {}
  ) {}

  start(kind: JobKind, params: Record<string, unknown>): string {
    if (this.active) throw new Error('Ya hay una operación de análisis o render en curso')
    const id = randomUUID()
    const script = join(this.appRoot, 'python', 'jobs.py')
    const executable = this.pythonExecutable
    const args = ['-u', script, kind, '--repo-root', this.repoRoot]
    const child = spawn(
      executable,
      args,
      {
        cwd: this.repoRoot,
        env: { ...process.env, ...this.extraEnv, PYTHONUTF8: '1', PYTHONUNBUFFERED: '1' },
        windowsHide: true
      }
    )
    const active: ActiveJob = { id, kind, process: child, terminalEventSeen: false }
    this.active = active
    this.report({ jobId: id, jobKind: kind, kind: 'started' })

    const lines = createInterface({ input: child.stdout })
    lines.on('line', (line) => {
      try {
        const payload = JSON.parse(line) as Omit<JobEvent, 'jobId' | 'jobKind'>
        if (payload.kind === 'completed' || payload.kind === 'failed') {
          active.terminalEventSeen = true
        }
        this.report({ ...payload, jobId: id, jobKind: kind })
      } catch {
        this.report({ jobId: id, jobKind: kind, kind: 'progress', message: line })
      }
    })

    let stderr = ''
    child.stderr.setEncoding('utf8')
    child.stderr.on('data', (chunk: string) => {
      stderr = `${stderr}${chunk}`.slice(-12_000)
    })
    child.on('error', (error) => {
      active.terminalEventSeen = true
      this.report({ jobId: id, jobKind: kind, kind: 'failed', error: error.message })
    })
    child.on('exit', (code) => {
      if (!active.terminalEventSeen) {
        this.report({
          jobId: id,
          jobKind: kind,
          kind: code === null ? 'cancelled' : 'failed',
          error: code === null ? undefined : `El proceso terminó con código ${code}`,
          detail: stderr || undefined
        })
      }
      if (this.active?.id === id) this.active = null
    })
    child.stdin.end(JSON.stringify(params))
    return id
  }

  cancel(jobId: string): boolean {
    const active = this.active
    if (!active || active.id !== jobId) return false
    active.terminalEventSeen = true
    if (process.platform === 'win32' && active.process.pid) {
      const killer = spawn('taskkill', ['/PID', String(active.process.pid), '/T', '/F'], {
        windowsHide: true
      })
      killer.on('error', () => active.process.kill())
    } else {
      active.process.kill('SIGTERM')
    }
    this.report({ jobId, jobKind: active.kind, kind: 'cancelled' })
    this.active = null
    return true
  }

  close(): void {
    if (this.active) this.cancel(this.active.id)
  }
}
