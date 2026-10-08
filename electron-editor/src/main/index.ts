import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import { electronApp, is, optimizer } from '@electron-toolkit/utils'
import type {
  AnalysisRequest,
  BatchRequest,
  EffectFramePreview,
  ProjectRenderSettingsPatch,
  ProjectView,
  RecentProject,
  RecoveryInfo,
  TimelineMedia,
  VisualEffectKind,
  VisualEffectRange
} from '../shared/contracts'
import { PythonBridge } from './bridge-client'
import { JobRunner, type JobEvent } from './job-runner'
import { LocalMediaServer } from './media-server'
import { setupSingleInstance } from './single-instance'
import { resolveBackendRuntime, type BackendRuntime } from './backend-runtime'
import { BackendSetupController, spawnRunner } from './macos-backend-setup'
import { readySetupStatus, type BackendSetupStatus } from '../shared/backend-setup'
import { withProjectPreviews } from './recent-project-previews'

interface RecoveryFile extends RecoveryInfo {
  payloadJson?: string
  payload?: Record<string, unknown>
}

const mediaServer = new LocalMediaServer()
app.setName('CREAcut Beta')
let bridge: PythonBridge | null = null
let jobs: JobRunner | null = null
let backendSetup: BackendSetupController | null = null

/**
 * Crea el bridge y el ejecutor de trabajos. En macOS empaquetado espera a que
 * la preparación del primer arranque deje listo el entorno; en Windows y en
 * desarrollo se llama de inmediato.
 */
function startBackend(runtime: BackendRuntime): void {
  if (bridge) return
  bridge = new PythonBridge(runtime.appRoot, runtime.repoRoot, runtime.pythonExecutable, runtime.env)
  jobs = new JobRunner(bridge.pythonExecutable(), runtime.appRoot, runtime.repoRoot, (event) => {
    void handleJobEvent(event)
  }, runtime.env)
}

/** Envía el estado de la preparación al renderer; nunca lanza (la ventana puede estar cerrada). */
function sendSetupStatus(status: BackendSetupStatus): void {
  if (!mainWindow || mainWindow.isDestroyed() || mainWindow.webContents.isDestroyed()) return
  mainWindow.webContents.send('backendSetup:progress', status)
}
let mainWindow: BrowserWindow | null = null
let currentProject: ProjectView | null = null
let allowWindowClose = false

function recentFile(): string {
  return join(app.getPath('userData'), 'recent-projects.json')
}

function recoveryFile(): string {
  return join(app.getPath('userData'), 'recovery-project.json')
}

function readJson<T>(filePath: string, fallback: T): T {
  try {
    return JSON.parse(readFileSync(filePath, 'utf8')) as T
  } catch {
    return fallback
  }
}

function clearRecovery(): void {
  const target = recoveryFile()
  if (existsSync(target)) unlinkSync(target)
}

function listRecent(): RecentProject[] {
  return readJson<RecentProject[]>(recentFile(), []).filter(
    (item) => typeof item?.path === 'string' && existsSync(item.path)
  )
}

function rememberProject(projectPath: string): void {
  const resolved = resolve(projectPath)
  const next: RecentProject[] = [
    {
      path: resolved,
      name: basename(resolved).replace(/\.creacut\.json$/i, ''),
      openedAt: new Date().toISOString()
    },
    ...listRecent().filter((item) => resolve(item.path) !== resolved)
  ].slice(0, 10)
  writeFileSync(recentFile(), JSON.stringify(next, null, 2), 'utf8')
}

function registerMediaPath(filePath: string): string {
  return mediaServer.register(filePath)
}

function exposeProjectMedia(project: ProjectView, preserveCurrent = true): ProjectView {
  if (!project.sourceExists || !project.sourcePath) {
    project.mediaUrl = null
  } else if (
    preserveCurrent &&
    currentProject?.sourcePath === project.sourcePath &&
    currentProject.mediaUrl
  ) {
    project.mediaUrl = currentProject.mediaUrl
  } else {
    project.mediaUrl = registerMediaPath(project.sourcePath)
  }
  if (project.slides) {
    project.slides = {
      ...project.slides,
      pages: project.slides.pages.map((page) => {
        const existing = preserveCurrent
          ? currentProject?.slides?.pages.find((item) => item.imagePath === page.imagePath)
          : undefined
        return {
          ...page,
          imageUrl: existing?.imageUrl ?? (existsSync(page.imagePath) ? registerMediaPath(page.imagePath) : null),
          thumbnailUrl: existing?.thumbnailUrl ?? (existsSync(page.thumbnailPath) ? registerMediaPath(page.thumbnailPath) : null)
        }
      })
    }
  }
  return project
}

async function checkpointRecovery(): Promise<void> {
  if (!currentProject?.dirty) {
    clearRecovery()
    return
  }
  const snapshot = await bridge!.request<{
    projectPath: string
    payloadJson: string
    dirty: boolean
  }>('snapshot')
  const recovery: RecoveryFile = {
    projectPath: snapshot.projectPath,
    projectName: basename(snapshot.projectPath).replace(/\.creacut\.json$/i, ''),
    savedAt: new Date().toISOString(),
    payloadJson: snapshot.payloadJson
  }
  writeFileSync(recoveryFile(), JSON.stringify(recovery), 'utf8')
}

async function updateFromBridge(
  method: string,
  params: Record<string, unknown> = {},
  checkpoint = true
): Promise<ProjectView> {
  const result = exposeProjectMedia(await bridge!.request<ProjectView>(method, params))
  currentProject = result
  if (checkpoint) await checkpointRecovery()
  return result
}

async function saveCurrent(saveAs = false): Promise<ProjectView | null> {
  if (!currentProject) throw new Error('No hay un proyecto abierto')
  let target: string | undefined
  if (saveAs) {
    const selection = await dialog.showSaveDialog(mainWindow!, {
      title: 'Guardar proyecto CREAcut como',
      defaultPath: currentProject.projectPath,
      filters: [{ name: 'Proyecto CREAcut', extensions: ['creacut.json', 'json'] }]
    })
    if (selection.canceled || !selection.filePath) return null
    target = selection.filePath.endsWith('.json')
      ? selection.filePath
      : `${selection.filePath}.creacut.json`
  }
  currentProject = exposeProjectMedia(
    await bridge!.request<ProjectView>('save_project', { path: target ?? null })
  )
  rememberProject(currentProject.projectPath)
  clearRecovery()
  return currentProject
}

async function confirmUnsaved(): Promise<boolean> {
  if (!currentProject?.dirty) return true
  const answer = await dialog.showMessageBox(mainWindow!, {
    type: 'warning',
    title: 'Cambios sin guardar',
    message: 'El proyecto tiene cambios sin guardar.',
    detail: 'Puedes guardarlos antes de continuar o descartarlos.',
    buttons: ['Guardar', 'Descartar', 'Cancelar'],
    defaultId: 0,
    cancelId: 2,
    noLink: true
  })
  if (answer.response === 2) return false
  if (answer.response === 0) {
    await saveCurrent(false)
  } else {
    clearRecovery()
    if (existsSync(currentProject.projectPath)) {
      currentProject = exposeProjectMedia(
        await bridge!.request<ProjectView>('open_project', { path: currentProject.projectPath })
      )
    }
  }
  return true
}

async function openProjectPath(projectPath: string, askToDiscard = true): Promise<ProjectView> {
  if (askToDiscard && !(await confirmUnsaved())) throw new Error('Apertura cancelada')
  mediaServer.clear()
  currentProject = exposeProjectMedia(
    await bridge!.request<ProjectView>('open_project', { path: projectPath }),
    false
  )
  rememberProject(currentProject.projectPath)
  clearRecovery()
  return currentProject
}

async function handleJobEvent(event: JobEvent): Promise<void> {
  const outgoing: JobEvent = { ...event }
  if (event.kind === 'completed' && event.jobKind === 'analysis') {
    const projectPath = event.result?.projectPath
    if (typeof projectPath === 'string') {
      try {
        const view = await openProjectPath(projectPath, false)
        outgoing.result = { ...event.result, projectView: view }
      } catch (error) {
        outgoing.kind = 'failed'
        outgoing.error = error instanceof Error ? error.message : String(error)
      }
    }
  }
  mainWindow?.webContents.send('job:event', outgoing)
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 940,
    minWidth: 1120,
    minHeight: 700,
    show: false,
    backgroundColor: '#0b0d12',
    title: 'CREAcut Beta',
    icon: app.isPackaged
      ? join(process.resourcesPath, 'icon.png')
      : join(__dirname, '../../resources/icon.png'),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })

  mainWindow.once('ready-to-show', () => {
    mainWindow?.maximize()
    mainWindow?.show()
  })
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  mainWindow.webContents.on('will-navigate', (event) => event.preventDefault())
  mainWindow.on('close', (event) => {
    if (allowWindowClose || !currentProject?.dirty) return
    event.preventDefault()
    void confirmUnsaved().then((mayClose) => {
      if (!mayClose) return
      allowWindowClose = true
      mainWindow?.close()
    })
  })

  if (is.dev && process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

async function pickPath(kind: string): Promise<string | null> {
  if (kind === 'project-output') {
    const selection = await dialog.showSaveDialog(mainWindow!, {
      title: 'Guardar nuevo proyecto CREAcut',
      filters: [{ name: 'Proyecto CREAcut', extensions: ['creacut.json', 'json'] }]
    })
    if (selection.canceled || !selection.filePath) return null
    return selection.filePath.endsWith('.json')
      ? selection.filePath
      : `${selection.filePath}.creacut.json`
  }
  if (kind === 'directory') {
    const selection = await dialog.showOpenDialog(mainWindow!, {
      title: 'Elegir carpeta',
      properties: ['openDirectory', 'createDirectory']
    })
    return selection.canceled ? null : selection.filePaths[0] ?? null
  }
  const filters: Record<string, Electron.FileFilter[]> = {
    video: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'm4v', 'avi', 'webm'] }],
    script: [{ name: 'Guion Markdown', extensions: ['md', 'markdown'] }],
    config: [{ name: 'Configuración YAML', extensions: ['yml', 'yaml'] }],
    image: [{ name: 'Imagen', extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'] }],
    slides: [{ name: 'Diapositivas', extensions: ['pptx', 'pdf'] }]
  }
  const selection = await dialog.showOpenDialog(mainWindow!, {
    title: `Seleccionar ${kind}`,
    properties: ['openFile'],
    filters: filters[kind] ?? [{ name: 'Todos los archivos', extensions: ['*'] }]
  })
  return selection.canceled ? null : selection.filePaths[0] ?? null
}

function registerIpc(): void {
  ipcMain.handle('backendSetup:status', () => backendSetup ? backendSetup.status() : readySetupStatus())
  ipcMain.handle('backendSetup:start', () => backendSetup ? backendSetup.start() : readySetupStatus())
  ipcMain.handle('bridge:status', () => bridge!.request('hello'))
  ipcMain.handle('bridge:device-status', () => bridge!.request('device_status', {}, 60_000))

  ipcMain.handle('project:open', async () => {
    if (!(await confirmUnsaved())) return null
    const selection = await dialog.showOpenDialog(mainWindow!, {
      title: 'Abrir proyecto CREAcut',
      properties: ['openFile'],
      filters: [
        { name: 'Proyecto CREAcut', extensions: ['json'] },
        { name: 'Todos los archivos', extensions: ['*'] }
      ]
    })
    if (selection.canceled || !selection.filePaths[0]) return null
    return openProjectPath(selection.filePaths[0], false)
  })
  ipcMain.handle('project:open-path', (_event, path: string) => openProjectPath(path))

  ipcMain.handle('project:locate-media', async () => {
    if (!currentProject) throw new Error('Primero abre un proyecto CREAcut')
    const selection = await dialog.showOpenDialog(mainWindow!, {
      title: 'Ubicar video fuente',
      defaultPath: dirname(currentProject.projectPath),
      properties: ['openFile'],
      filters: [
        { name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'm4v', 'avi', 'webm'] },
        { name: 'Todos los archivos', extensions: ['*'] }
      ]
    })
    if (selection.canceled || !selection.filePaths[0]) return null
    mediaServer.clear()
    currentProject = exposeProjectMedia(
      await bridge!.request<ProjectView>('locate_media', { path: selection.filePaths[0] }),
      false
    )
    return currentProject
  })

  ipcMain.handle('project:select-candidate', (_event, value: { segmentId: string; candidateId: string }) =>
    updateFromBridge('select_candidate', { segment_id: value.segmentId, candidate_id: value.candidateId })
  )
  ipcMain.handle('project:restore-candidate', (_event, segmentId: string) =>
    updateFromBridge('restore_candidate', { segment_id: segmentId })
  )
  ipcMain.handle('project:mark-region', (_event, value: { regionId: string; keep: boolean }) =>
    updateFromBridge('timeline_mark', { region_id: value.regionId, keep: value.keep })
  )
  ipcMain.handle('project:restore-region', (_event, regionId: string) =>
    updateFromBridge('timeline_restore', { region_id: regionId })
  )
  ipcMain.handle('project:split-timeline', (_event, sourceTimeS: number) =>
    updateFromBridge('timeline_split', { source_time_s: sourceTimeS })
  )
  ipcMain.handle('project:move-boundary', (_event, value: { oldSourceTimeS: number; newSourceTimeS: number }) =>
    updateFromBridge('timeline_move_boundary', {
      old_source_time_s: value.oldSourceTimeS,
      new_source_time_s: value.newSourceTimeS
    })
  )
  ipcMain.handle('project:update-render-settings', (_event, patch: ProjectRenderSettingsPatch) =>
    updateFromBridge('update_render_settings', { patch })
  )
  ipcMain.handle('project:add-effect-range', (_event, value: { kind: VisualEffectKind; startS: number; endS: number }) =>
    updateFromBridge('add_effect_range', { kind: value.kind, start_s: value.startS, end_s: value.endS })
  )
  ipcMain.handle('project:update-effect-range', (_event, value: { effectId: string; patch: Partial<Pick<VisualEffectRange, 'kind' | 'startS' | 'endS'>> }) =>
    updateFromBridge('update_effect_range', {
      effect_id: value.effectId,
      kind: value.patch.kind,
      start_s: value.patch.startS,
      end_s: value.patch.endS
    })
  )
  ipcMain.handle('project:delete-effect-range', (_event, effectId: string) =>
    updateFromBridge('delete_effect_range', { effect_id: effectId })
  )
  ipcMain.handle('project:import-slide-source', (_event, sourcePath: string) =>
    updateFromBridge('import_slide_source', { source_path: sourcePath })
  )
  ipcMain.handle('project:remove-slide-source', () =>
    updateFromBridge('remove_slide_source')
  )
  ipcMain.handle('project:recommend-slides', () => updateFromBridge('recommend_slides'))
  ipcMain.handle('project:accept-slide-recommendations', () =>
    updateFromBridge('accept_slide_recommendations')
  )
  ipcMain.handle('project:update-slide-page', (_event, { pageId, patch }) =>
    updateFromBridge('update_slide_page', { page_id: pageId, patch })
  )
  ipcMain.handle('project:preview-effects-frame', async (_event, sourceTimeS: number): Promise<EffectFramePreview> => {
    if (!currentProject) throw new Error('Primero abre un proyecto CREAcut')
    const result = await bridge!.request<{
      path: string
      presenterPath: string | null
      timeS: number
      slidePageId: string | null
    }>('preview_effects_frame', { source_time_s: sourceTimeS }, 120_000)
    return {
      url: registerMediaPath(result.path),
      presenterUrl: result.presenterPath ? registerMediaPath(result.presenterPath) : null,
      timeS: result.timeS,
      slidePageId: result.slidePageId
    }
  })
  ipcMain.handle('project:undo', () => updateFromBridge('timeline_undo'))
  ipcMain.handle('project:redo', () => updateFromBridge('timeline_redo'))
  ipcMain.handle('project:save', (_event, saveAs: boolean) => saveCurrent(saveAs))
  ipcMain.handle('project:close', async () => {
    if (!currentProject) return true
    if (!(await confirmUnsaved())) return false
    await bridge!.request('close_project')
    currentProject = null
    mediaServer.clear()
    clearRecovery()
    return true
  })

  ipcMain.handle(
    'project:timeline-media',
    async (_event, options: { sampleCount: number; waveformBuckets: number }) => {
      if (!currentProject) throw new Error('Primero abre un proyecto CREAcut')
      const result = await bridge!.request<{
        thumbnails: Array<{ timeS: number; path: string }>
        waveform: number[]
        warning: string | null
      }>(
        'timeline_media',
        { sample_count: options.sampleCount, waveform_buckets: options.waveformBuckets },
        300_000
      )
      const exposed: TimelineMedia = {
        thumbnails: result.thumbnails
          .filter((item) => existsSync(item.path))
          .map((item) => ({ timeS: item.timeS, url: registerMediaPath(item.path) })),
        waveform: result.waveform,
        warning: result.warning
      }
      return exposed
    }
  )

  ipcMain.handle('dialog:pick-path', (_event, kind: string) => pickPath(kind))
  ipcMain.handle('dialog:pick-batch-files', async (_event, kind: 'videos' | 'scripts') => {
    const video = kind === 'videos'
    const selection = await dialog.showOpenDialog(mainWindow!, {
      title: video ? 'Seleccionar videos del lote' : 'Seleccionar guiones del lote',
      properties: ['openFile', 'multiSelections'],
      filters: video
        ? [{ name: 'Videos', extensions: ['mp4', 'mov', 'mkv', 'm4v', 'avi', 'webm'] }]
        : [{ name: 'Guiones Markdown', extensions: ['md', 'markdown'] }]
    })
    return selection.canceled ? [] : selection.filePaths
  })

  ipcMain.handle('job:start-analysis', async (_event, request: AnalysisRequest) => {
    if (!(await confirmUnsaved())) throw new Error('Análisis cancelado')
    let allowReplace = false
    if (existsSync(request.projectPath)) {
      const answer = await dialog.showMessageBox(mainWindow!, {
        type: 'warning',
        title: 'Reemplazar proyecto',
        message: 'Ya existe un archivo en la ruta seleccionada.',
        detail: request.projectPath,
        buttons: ['Reemplazar', 'Cancelar'],
        defaultId: 1,
        cancelId: 1,
        noLink: true
      })
      if (answer.response !== 0) throw new Error('Análisis cancelado')
      allowReplace = true
    }
    return jobs!.start('analysis', {
      video_path: request.videoPath,
      script_path: request.scriptPath,
      project_path: request.projectPath,
      config_path: request.configPath ?? null,
      background_image: request.backgroundImage ?? null,
      allow_replace: allowReplace
    })
  })
  ipcMain.handle('job:start-render', async () => {
    if (!currentProject) throw new Error('Primero abre un proyecto CREAcut')
    if (currentProject.dirty) await saveCurrent(false)
    const defaultOutput = currentProject.projectPath.replace(/\.creacut\.json$/i, '-final.mp4')
    const selection = await dialog.showSaveDialog(mainWindow!, {
      title: 'Exportar MP4',
      defaultPath: defaultOutput,
      filters: [{ name: 'Video MP4', extensions: ['mp4'] }]
    })
    if (selection.canceled || !selection.filePath) return null
    return jobs!.start('render', {
      project_path: currentProject.projectPath,
      output_path: selection.filePath.endsWith('.mp4')
        ? selection.filePath
        : `${selection.filePath}.mp4`
    })
  })
  ipcMain.handle(
    'job:start-batch',
    (_event, value: BatchRequest) =>
      jobs!.start('batch', {
        video_paths: value.videoPaths,
        script_paths: value.scriptPaths,
        output_directory: value.outputDirectory
      })
  )
  ipcMain.handle('job:cancel', (_event, jobId: string) => jobs!.cancel(jobId))

  ipcMain.handle('recent:list', () => Promise.all(listRecent().map((project) => withProjectPreviews(project, registerMediaPath))))
  ipcMain.handle('recovery:info', () => {
    const recovery = readJson<RecoveryFile | null>(recoveryFile(), null)
    if ((!recovery?.payloadJson && !recovery?.payload) || !recovery.projectPath) return null
    const { payload: _payload, payloadJson: _payloadJson, ...info } = recovery
    return info
  })
  ipcMain.handle('recovery:restore', async () => {
    const recovery = readJson<RecoveryFile | null>(recoveryFile(), null)
    if (!recovery?.payloadJson && !recovery?.payload) return null
    try {
      mediaServer.clear()
      currentProject = exposeProjectMedia(
        await bridge!.request<ProjectView>('restore_snapshot', {
          project_path: recovery.projectPath,
          payload_json: recovery.payloadJson ?? null,
          payload: recovery.payload ?? null
        }),
        false
      )
      return currentProject
    } catch (error) {
      console.error('No se pudo restaurar la recuperación automática:', error)
      throw new Error(
        'No se pudo recuperar la copia automática porque no corresponde al proyecto guardado. El archivo original sigue intacto y puedes abrirlo desde Proyectos recientes.'
      )
    }
  })
}

const isPrimaryInstance = setupSingleInstance(
  () => app.requestSingleInstanceLock(),
  (listener) => app.on('second-instance', listener),
  () => mainWindow
)

if (!isPrimaryInstance) {
  app.quit()
} else {
  app.whenReady().then(async () => {
    electronApp.setAppUserModelId('com.crea.creacut')
    app.on('browser-window-created', (_, window) => optimizer.watchWindowShortcuts(window))
    const runtime = resolveBackendRuntime({
      packaged: app.isPackaged,
      appRoot: app.getAppPath(),
      resourcesPath: process.resourcesPath
    })
    if (runtime.setup) {
      backendSetup = new BackendSetupController(
        runtime.setup,
        spawnRunner,
        sendSetupStatus,
        () => startBackend(runtime)
      )
    } else {
      startBackend(runtime)
    }

    await mediaServer.start()

    registerIpc()
    createWindow()
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
  })

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })

  app.on('will-quit', () => {
    // Si se cierra a mitad de la preparación, uv y Python no pueden seguir
    // escribiendo en el .venv que el siguiente arranque va a reconstruir.
    backendSetup?.cancel()
    void mediaServer.close()
    jobs?.close()
    bridge?.close()
  })
}
