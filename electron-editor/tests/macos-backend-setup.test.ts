import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { BackendSetupPaths } from '../src/main/backend-runtime'
import {
  BackendSetupController,
  checkEnvironment,
  markerPath,
  runSetup,
  SetupCancelledError,
  SetupStepError,
  setupEnvironment,
  spawnRunner,
  venvPython,
  type CommandRunner,
  type RunOptions
} from '../src/main/macos-backend-setup'
import type { BackendSetupProgress, BackendSetupStatus } from '../src/shared/backend-setup'

interface Call { executable: string; args: string[]; env: NodeJS.ProcessEnv; timeoutMs?: number; signal?: AbortSignal }
type Script = (executable: string, args: string[]) => { code?: number; lines?: string[]; error?: Error }

class FakeRunner implements CommandRunner {
  calls: Call[] = []
  constructor(private readonly script: Script = () => ({ code: 0 })) {}
  async run(executable: string, args: string[], options: RunOptions): Promise<number> {
    this.calls.push({ executable, args, env: options.env, timeoutMs: options.timeoutMs, signal: options.signal })
    const result = this.script(executable, args)
    if (result.error) throw result.error
    for (const line of result.lines ?? []) options.onLine(line)
    return result.code ?? 0
  }
}

function fixture(version = '0.3.0'): BackendSetupPaths {
  const root = mkdtempSync(join(tmpdir(), 'creacut-setup-'))
  const resources = join(root, 'Resources')
  mkdirSync(join(resources, 'backend-setup'), { recursive: true })
  writeFileSync(join(resources, 'backend-setup', 'manifest.json'), JSON.stringify({ version, pythonVersion: '3.12' }))
  return {
    uv: join(resources, 'backend-setup', 'uv'),
    manifestPath: join(resources, 'backend-setup', 'manifest.json'),
    runtimeDirectory: join(root, 'runtime'),
    backendRoot: join(resources, 'backend'),
    logPath: join(root, 'Logs', 'backend-setup.log')
  }
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

async function exitsWithin(pid: number, ms: number): Promise<boolean> {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    if (!isAlive(pid)) return true
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  return !isAlive(pid)
}

function writeEnvironment(paths: BackendSetupPaths, marker: string | null): void {
  mkdirSync(join(paths.runtimeDirectory, '.venv', 'bin'), { recursive: true })
  writeFileSync(venvPython(paths.runtimeDirectory), '')
  if (marker !== null) writeFileSync(markerPath(paths.runtimeDirectory), marker)
}

describe('runSetup', () => {
  it('ejecuta los cinco pasos en orden con uv y el Python del entorno', async () => {
    const paths = fixture()
    const runner = new FakeRunner()
    await runSetup(paths, runner, () => {})
    const venv = join(paths.runtimeDirectory, '.venv')
    const python = venvPython(paths.runtimeDirectory)

    expect(runner.calls.map((call) => [call.executable, call.args])).toEqual([
      [paths.uv, ['venv', venv, '--python', '3.12', '--python-preference', 'only-managed']],
      [paths.uv, ['pip', 'install', '--python', python, 'torch']],
      [paths.uv, ['pip', 'install', '--python', python, '-r', join(paths.backendRoot, 'python', 'requirements-runtime.txt')]],
      [python, [join(paths.backendRoot, 'python', 'verify_backend.py')]],
      [python, [join(paths.backendRoot, 'python', 'setup_models.py'), '--solo-whisper']]
    ])
  })

  it('pasa las variables de uv y de Python a cada comando', async () => {
    const paths = fixture()
    const runner = new FakeRunner()
    await runSetup(paths, runner, () => {})
    for (const call of runner.calls) {
      expect(call.env).toMatchObject({
        UV_PYTHON_INSTALL_DIR: join(paths.runtimeDirectory, 'python'),
        UV_NO_PROGRESS: '1',
        UV_HTTP_TIMEOUT: '180',
        PYTHONUTF8: '1',
        PYTHONUNBUFFERED: '1'
      })
    }
  })

  it('escribe el marcador con la versión solo al terminar', async () => {
    const paths = fixture('0.3.0')
    let markerDuringWhisper: boolean | null = null
    const runner = new FakeRunner((_executable, args) => {
      if (args.includes('--solo-whisper')) markerDuringWhisper = existsSync(markerPath(paths.runtimeDirectory))
      return { code: 0 }
    })
    await runSetup(paths, runner, () => {})

    expect(markerDuringWhisper).toBe(false)
    const marker = JSON.parse(readFileSync(markerPath(paths.runtimeDirectory), 'utf8'))
    expect(marker).toMatchObject({ version: '0.3.0', pythonVersion: '3.12' })
    expect(typeof marker.installedAt).toBe('string')
  })

  it('borra el marcador y el .venv anteriores antes de empezar', async () => {
    const paths = fixture()
    writeEnvironment(paths, JSON.stringify({ version: '0.1.0' }))
    writeFileSync(join(paths.runtimeDirectory, '.venv', 'resto-viejo'), 'x')
    let markerAtStart: boolean | null = null
    let leftoverAtStart: boolean | null = null
    const runner = new FakeRunner((_executable, args) => {
      if (args[0] === 'venv') {
        markerAtStart = existsSync(markerPath(paths.runtimeDirectory))
        leftoverAtStart = existsSync(join(paths.runtimeDirectory, '.venv', 'resto-viejo'))
      }
      return { code: 0 }
    })
    await runSetup(paths, runner, () => {})
    expect(markerAtStart).toBe(false)
    expect(leftoverAtStart).toBe(false)
  })

  it('un paso que falla detiene la preparación, informa y no deja marcador', async () => {
    const paths = fixture()
    const events: BackendSetupProgress[] = []
    const runner = new FakeRunner((_executable, args) =>
      args.includes('torch') ? { code: 1, lines: ['error: Failed to fetch torch', 'Connection reset'] } : { code: 0 }
    )

    const failure = await runSetup(paths, runner, (event) => events.push(event)).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(SetupStepError)
    expect((failure as SetupStepError).stepId).toBe('torch')
    expect((failure as SetupStepError).message).toBe('No se pudo instalar PyTorch.')
    expect((failure as SetupStepError).detail).toContain('Connection reset')
    expect(runner.calls).toHaveLength(2)
    expect(existsSync(markerPath(paths.runtimeDirectory))).toBe(false)
    expect(events.at(-1)).toEqual({ stepId: 'torch', state: 'failed', message: 'No se pudo instalar PyTorch.' })
  })

  it('un comando que no se puede lanzar cuenta como fallo del paso', async () => {
    const paths = fixture()
    const runner = new FakeRunner(() => ({ error: Object.assign(new Error('spawn EACCES'), { code: 'EACCES' }) }))

    const failure = await runSetup(paths, runner, () => {}).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(SetupStepError)
    expect((failure as SetupStepError).stepId).toBe('python')
    expect((failure as SetupStepError).detail).toContain('spawn EACCES')
  })

  it('si uv no se puede lanzar, el mensaje lo dice y el fallo es de lanzamiento', async () => {
    const paths = fixture()
    const events: BackendSetupProgress[] = []
    const runner = new FakeRunner(() => ({ error: Object.assign(new Error('spawn EPERM'), { code: 'EPERM' }) }))
    const failure = await runSetup(paths, runner, (event) => events.push(event)).catch((error: unknown) => error) as SetupStepError
    expect(failure.message).toBe('No se pudo ejecutar uv, el instalador de Python que viene con CREAcut.')
    expect(failure.kind).toBe('launch')
    expect(events.at(-1)).toEqual({ stepId: 'python', state: 'failed', message: failure.message })
  })

  it('si el Python del entorno no se puede lanzar, el mensaje habla de Python', async () => {
    const paths = fixture()
    const python = venvPython(paths.runtimeDirectory)
    const runner = new FakeRunner((executable) =>
      executable === python ? { error: Object.assign(new Error('spawn ENOENT'), { code: 'ENOENT' }) } : { code: 0 }
    )
    const failure = await runSetup(paths, runner, () => {}).catch((error: unknown) => error) as SetupStepError
    expect(failure.stepId).toBe('verify')
    expect(failure.message).toBe('No se pudo ejecutar Python del entorno.')
    expect(failure.kind).toBe('launch')
  })

  it('un código de salida distinto de 0 es un fallo del paso, no de lanzamiento', async () => {
    const paths = fixture()
    const runner = new FakeRunner((_executable, args) => (args.includes('torch') ? { code: 1 } : { code: 0 }))
    const failure = await runSetup(paths, runner, () => {}).catch((error: unknown) => error) as SetupStepError
    expect(failure.kind).toBe('step')
  })

  it('informa líneas y el porcentaje de Whisper, y deja el registro en disco', async () => {
    const paths = fixture()
    const events: BackendSetupProgress[] = []
    const runner = new FakeRunner((_executable, args) =>
      args.includes('--solo-whisper') ? { lines: ['Descargando large-v3.pt...', 'large-v3.pt: 42%'] } : { code: 0 }
    )
    await runSetup(paths, runner, (event) => events.push(event))

    expect(events).toContainEqual({ stepId: 'whisper', state: 'running', message: 'large-v3.pt: 42%', percent: 42 })
    expect(events).toContainEqual({ stepId: 'whisper', state: 'running', message: 'Descargando large-v3.pt...', percent: undefined })
    expect(readFileSync(paths.logPath, 'utf8')).toContain('large-v3.pt: 42%')
  })
})

describe('setupEnvironment', () => {
  it('aísla uv y Python del entorno del usuario y deja los .pyc fuera del .app', () => {
    const paths = fixture()
    const saved = { PYTHONPATH: process.env.PYTHONPATH, PYTHONHOME: process.env.PYTHONHOME, VIRTUAL_ENV: process.env.VIRTUAL_ENV }
    Object.assign(process.env, { PYTHONPATH: '/otro', PYTHONHOME: '/otro', VIRTUAL_ENV: '/otro/.venv' })
    try {
      const env = setupEnvironment(paths)
      expect(env).toMatchObject({
        UV_NO_CONFIG: '1',
        PYTHONPYCACHEPREFIX: join(paths.runtimeDirectory, 'pycache')
      })
      expect(env).not.toHaveProperty('PYTHONPATH')
      expect(env).not.toHaveProperty('PYTHONHOME')
      expect(env).not.toHaveProperty('VIRTUAL_ENV')
    } finally {
      for (const [key, value] of Object.entries(saved)) {
        if (value === undefined) delete process.env[key]
        else process.env[key] = value
      }
    }
  })
})

describe('registro no escribible', () => {
  it('la preparación termina aunque no se pueda escribir el registro', async () => {
    const paths = fixture()
    const blocker = join(paths.runtimeDirectory, '..', 'bloqueo')
    writeFileSync(blocker, 'archivo')
    paths.logPath = join(blocker, 'Logs', 'backend-setup.log')
    await runSetup(paths, new FakeRunner(), () => {})
    expect(existsSync(markerPath(paths.runtimeDirectory))).toBe(true)
  })
})

describe('checkEnvironment', () => {
  const verifyOk = (): FakeRunner => new FakeRunner(() => ({ code: 0 }))

  it('está listo con marcador de la misma versión y verificación en 0', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0', pythonVersion: '3.12' }))
    const runner = verifyOk()
    expect(await checkEnvironment(paths, runner)).toBe('ready')
    expect(runner.calls).toEqual([
      expect.objectContaining({ executable: venvPython(paths.runtimeDirectory), args: [join(paths.backendRoot, 'python', 'verify_backend.py')] })
    ])
  })

  it.each([
    ['sin marcador', null],
    ['marcador de otra versión', JSON.stringify({ version: '0.2.0' })],
    ['marcador corrupto', '{no es json']
  ])('necesita preparación: %s', async (_name, marker) => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, marker)
    expect(await checkEnvironment(paths, verifyOk())).toBe('needs-setup')
  })

  it('necesita preparación si la verificación falla', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0' }))
    expect(await checkEnvironment(paths, new FakeRunner(() => ({ code: 1 })))).toBe('needs-setup')
  })

  it('la verificación tiene tiempo máximo y deja su salida en el registro', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0' }))
    const runner = new FakeRunner(() => ({ code: 0, lines: ['torch 2.8.0 (CPU)'] }))
    expect(await checkEnvironment(paths, runner)).toBe('ready')
    expect(runner.calls[0].timeoutMs).toBe(120_000)
    const log = readFileSync(paths.logPath, 'utf8')
    expect(log).toMatch(/^== verify/m)
    expect(log).toContain('torch 2.8.0 (CPU)')
  })

  it('una verificación que se pasa del tiempo cuenta como necesita preparación', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0' }))
    const runner = new FakeRunner(() => ({ error: Object.assign(new Error('El comando superó el tiempo máximo (120 s).'), { code: 'ETIMEDOUT' }) }))
    expect(await checkEnvironment(paths, runner)).toBe('needs-setup')
    expect(readFileSync(paths.logPath, 'utf8')).toContain('tiempo máximo')
  })

  it('necesita preparación si no hay entorno en absoluto', async () => {
    const paths = fixture()
    const runner = verifyOk()
    expect(await checkEnvironment(paths, runner)).toBe('needs-setup')
    expect(runner.calls).toEqual([])
  })
})

describe('BackendSetupController', () => {
  it('dos start simultáneos ejecutan una sola preparación y avisan listo una vez', async () => {
    const paths = fixture()
    const runner = new FakeRunner()
    const emitted: BackendSetupStatus[] = []
    let readyCalls = 0
    const controller = new BackendSetupController(paths, runner, (status) => emitted.push(status), () => readyCalls++)

    const [first, second] = await Promise.all([controller.start(), controller.start()])

    expect(first.state).toBe('ready')
    expect(second.state).toBe('ready')
    expect(runner.calls.filter((call) => call.args[0] === 'venv')).toHaveLength(1)
    expect(readyCalls).toBe(1)
    expect(emitted[0].state).toBe('running')
    expect(emitted.at(-1)?.state).toBe('ready')
  })

  it('tras un fallo informa error y detalle, y Reintentar vuelve a empezar', async () => {
    const paths = fixture()
    let failTorch = true
    const runner = new FakeRunner((_executable, args) =>
      failTorch && args.includes('torch') ? { code: 1, lines: ['sin red'] } : { code: 0 }
    )
    let readyCalls = 0
    const controller = new BackendSetupController(paths, runner, () => {}, () => readyCalls++)

    const failed = await controller.start()
    expect(failed).toMatchObject({ state: 'failed', error: 'No se pudo instalar PyTorch.', errorKind: 'step', logPath: paths.logPath })
    expect(failed.detail).toContain('sin red')
    expect(readyCalls).toBe(0)

    failTorch = false
    const ready = await controller.start()
    expect(ready.state).toBe('ready')
    expect(readyCalls).toBe(1)
  })

  it('status detecta un entorno ya preparado y arranca el backend', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0' }))
    let readyCalls = 0
    const controller = new BackendSetupController(paths, new FakeRunner(), () => {}, () => readyCalls++)

    expect((await controller.status()).state).toBe('ready')
    expect((await controller.status()).state).toBe('ready')
    expect(readyCalls).toBe(1)
  })

  it('status que corre a la vez que start no marca listo ni arranca el backend antes de tiempo', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0' }))
    let releaseVerify: () => void = () => {}
    const verifyGate = new Promise<void>((resolve) => { releaseVerify = resolve })
    const runner = new FakeRunner()
    const original = runner.run.bind(runner)
    let gated = false
    runner.run = async (executable, args, options) => {
      // Solo la primera verificación (la de status) espera la compuerta.
      if (!gated && executable === venvPython(paths.runtimeDirectory) && args.length === 1) {
        gated = true
        runner.calls.push({ executable, args, env: options.env })
        await verifyGate
        return 0
      }
      return original(executable, args, options)
    }
    let readyCalls = 0
    const controller = new BackendSetupController(paths, runner, () => {}, () => readyCalls++)

    const pending = controller.status()
    const started = controller.start()
    releaseVerify()
    await pending
    expect(readyCalls).toBe(0)
    expect((await started).state).toBe('ready')
    expect(readyCalls).toBe(1)
  })

  it('status simultáneos comparten una sola verificación', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0' }))
    const runner = new FakeRunner()
    let readyCalls = 0
    const controller = new BackendSetupController(paths, runner, () => {}, () => readyCalls++)
    const [a, b] = await Promise.all([controller.status(), controller.status()])
    expect([a.state, b.state]).toEqual(['ready', 'ready'])
    expect(runner.calls).toHaveLength(1)
    expect(readyCalls).toBe(1)
  })

  it('un error antes del primer paso informa en español y deja el detalle crudo', async () => {
    const paths = fixture()
    writeFileSync(paths.manifestPath, '{no es json')
    const controller = new BackendSetupController(paths, new FakeRunner(), () => {}, () => {})
    const failed = await controller.start()
    expect(failed.state).toBe('failed')
    expect(failed.error).toBe('No se pudo iniciar la preparación.')
    expect(failed.errorKind).toBe('start')
    expect(failed.detail).toBeTruthy()
  })

  it('un fallo al lanzar uv llega a la pantalla como fallo de lanzamiento', async () => {
    const paths = fixture()
    const runner = new FakeRunner(() => ({ error: Object.assign(new Error('spawn EACCES'), { code: 'EACCES' }) }))
    const failed = await new BackendSetupController(paths, runner, () => {}, () => {}).start()
    expect(failed).toMatchObject({
      state: 'failed',
      errorKind: 'launch',
      error: 'No se pudo ejecutar uv, el instalador de Python que viene con CREAcut.'
    })
  })

  it('un fallo se emite una sola vez y ya trae el error', async () => {
    const paths = fixture()
    const emitted: BackendSetupStatus[] = []
    const runner = new FakeRunner((_e, args) => (args.includes('torch') ? { code: 1, lines: ['sin red'] } : { code: 0 }))
    const controller = new BackendSetupController(paths, runner, (status) => emitted.push(status), () => {})
    await controller.start()
    const failures = emitted.filter((status) => status.state === 'failed')
    expect(failures).toHaveLength(1)
    expect(failures[0].error).toBeTruthy()
    expect(failures[0].steps[1].state).toBe('failed')
  })

  it('cancel detiene el comando en curso y no deja marcador', async () => {
    const paths = fixture()
    const runner = new FakeRunner()
    const original = runner.run.bind(runner)
    let torchStarted: () => void = () => {}
    const torchRunning = new Promise<void>((resolve) => { torchStarted = resolve })
    runner.run = (executable, args, options) => {
      if (!args.includes('torch')) return original(executable, args, options)
      runner.calls.push({ executable, args, env: options.env, signal: options.signal })
      torchStarted()
      // Como spawnRunner: la señal mata el proceso y la promesa rechaza.
      return new Promise<number>((_resolve, reject) => {
        options.signal?.addEventListener('abort', () => reject(new SetupCancelledError()))
      })
    }
    let readyCalls = 0
    const controller = new BackendSetupController(paths, runner, () => {}, () => readyCalls++)

    const started = controller.start()
    await torchRunning
    controller.cancel()
    const final = await started

    expect(final.state).toBe('failed')
    expect(readyCalls).toBe(0)
    expect(runner.calls.map((call) => call.args[0])).toEqual(['venv', 'pip'])
    expect(existsSync(markerPath(paths.runtimeDirectory))).toBe(false)
  })

  it('un comando que termina bien justo al cancelar no deja seguir ni escribir el marcador', async () => {
    const paths = fixture()
    let controller: BackendSetupController | null = null
    const runner = new FakeRunner((_executable, args) => {
      // El runner ignora la señal: la orquestación tiene que frenar igual.
      if (args.includes('torch')) controller?.cancel()
      return { code: 0 }
    })
    controller = new BackendSetupController(paths, runner, () => {}, () => {})
    const final = await controller.start()
    expect(final.state).toBe('failed')
    expect(runner.calls).toHaveLength(2)
    expect(existsSync(markerPath(paths.runtimeDirectory))).toBe(false)
  })

  it('status no pisa con listo un fallo rápido de un start simultáneo', async () => {
    const paths = fixture('0.3.0')
    writeEnvironment(paths, JSON.stringify({ version: '0.3.0' }))
    let releaseVerify: () => void = () => {}
    const verifyGate = new Promise<void>((resolve) => { releaseVerify = resolve })
    const runner = new FakeRunner()
    runner.run = async (executable, args, options) => {
      runner.calls.push({ executable, args, env: options.env })
      await verifyGate
      return 0
    }
    let readyCalls = 0
    const controller = new BackendSetupController(paths, runner, () => {}, () => readyCalls++)

    const pending = controller.status()
    // El manifiesto se daña después de que status lo leyó: start falla al instante.
    writeFileSync(paths.manifestPath, '{no es json')
    expect((await controller.start()).state).toBe('failed')
    releaseVerify()
    expect((await pending).state).toBe('failed')
    expect(readyCalls).toBe(0)
  })

  it('status informa needs-setup sin empezar nada', async () => {
    const paths = fixture()
    const runner = new FakeRunner()
    const controller = new BackendSetupController(paths, runner, () => {}, () => {})
    expect((await controller.status()).state).toBe('needs-setup')
    expect(runner.calls).toEqual([])
  })
})

describe('spawnRunner', () => {
  it('reenvía las líneas no vacías de stdout y stderr y devuelve el código de salida', async () => {
    const lines: string[] = []
    const code = await spawnRunner.run(
      process.execPath,
      ['-e', "console.log('uno'); console.log(''); console.error('dos'); process.exit(3)"],
      { env: process.env, onLine: (line) => lines.push(line) }
    )
    expect(code).toBe(3)
    expect(lines.sort()).toEqual(['dos', 'uno'])
  })

  it('rechaza si onLine lanza, sin excepción no capturada', async () => {
    await expect(
      spawnRunner.run(process.execPath, ['-e', "console.log('x')"], {
        env: process.env,
        onLine: () => { throw new Error('disco lleno') }
      })
    ).rejects.toThrow('disco lleno')
  })

  it('cancelar con la señal mata el proceso y rechaza enseguida', async () => {
    const abort = new AbortController()
    let pid = 0
    const startedAt = Date.now()
    const run = spawnRunner.run(process.execPath, ['-e', 'console.log(String(process.pid)); setTimeout(() => {}, 60000)'], {
      env: process.env,
      signal: abort.signal,
      onLine: (line) => {
        // Solo la línea del pid: Node puede escribir avisos propios por stderr.
        if (!/^\d+$/.test(line)) return
        pid = Number(line)
        abort.abort()
      }
    })
    await expect(run).rejects.toBeInstanceOf(SetupCancelledError)
    expect(Date.now() - startedAt).toBeLessThan(10_000)
    expect(pid).toBeGreaterThan(0)
    expect(await exitsWithin(pid, 5_000)).toBe(true)
  })

  it('timeoutMs mata el proceso que se pasa del tiempo y rechaza', async () => {
    let pid = 0
    const startedAt = Date.now()
    const run = spawnRunner.run(process.execPath, ['-e', 'console.log(String(process.pid)); setTimeout(() => {}, 60000)'], {
      env: process.env,
      timeoutMs: 500,
      onLine: (line) => { if (/^\d+$/.test(line)) pid = Number(line) }
    })
    await expect(run).rejects.toThrow(/tiempo máximo/)
    expect(Date.now() - startedAt).toBeLessThan(10_000)
    expect(pid).toBeGreaterThan(0)
    expect(await exitsWithin(pid, 5_000)).toBe(true)
  })

  it('timeoutMs no afecta a un comando que termina a tiempo', async () => {
    expect(await spawnRunner.run(process.execPath, ['-e', 'process.exit(0)'], {
      env: process.env, timeoutMs: 30_000, onLine: () => {}
    })).toBe(0)
  })

  it('con la señal ya cancelada no lanza nada', async () => {
    const abort = new AbortController()
    abort.abort()
    const lines: string[] = []
    await expect(spawnRunner.run(process.execPath, ['-e', "console.log('no')"], {
      env: process.env, signal: abort.signal, onLine: (line) => lines.push(line)
    })).rejects.toBeInstanceOf(SetupCancelledError)
    expect(lines).toEqual([])
  })

  it('rechaza si el ejecutable no existe', async () => {
    await expect(spawnRunner.run(join(tmpdir(), 'no-existe-creacut'), [], { env: process.env, onLine: () => {} })).rejects.toThrow()
  })
})
