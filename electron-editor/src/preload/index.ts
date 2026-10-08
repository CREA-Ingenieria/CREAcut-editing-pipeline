import { contextBridge, ipcRenderer } from 'electron'
import type { CreacutApi } from '../shared/contracts'

const api: CreacutApi = {
  backendSetupStatus: () => ipcRenderer.invoke('backendSetup:status'),
  startBackendSetup: () => ipcRenderer.invoke('backendSetup:start'),
  onBackendSetupProgress: (callback) => {
    ipcRenderer.removeAllListeners('backendSetup:progress')
    ipcRenderer.on('backendSetup:progress', (_event, status) => callback(status))
  },
  bridgeStatus: () => ipcRenderer.invoke('bridge:status'),
  deviceStatus: () => ipcRenderer.invoke('bridge:device-status'),
  openProject: () => ipcRenderer.invoke('project:open'),
  openProjectPath: (path) => ipcRenderer.invoke('project:open-path', path),
  locateMedia: () => ipcRenderer.invoke('project:locate-media'),
  loadTimelineMedia: (sampleCount, waveformBuckets) =>
    ipcRenderer.invoke('project:timeline-media', { sampleCount, waveformBuckets }),
  selectCandidate: (segmentId, candidateId) =>
    ipcRenderer.invoke('project:select-candidate', { segmentId, candidateId }),
  restoreCandidate: (segmentId) => ipcRenderer.invoke('project:restore-candidate', segmentId),
  markRegion: (regionId, keep) => ipcRenderer.invoke('project:mark-region', { regionId, keep }),
  restoreRegion: (regionId) => ipcRenderer.invoke('project:restore-region', regionId),
  splitTimeline: (sourceTimeS) => ipcRenderer.invoke('project:split-timeline', sourceTimeS),
  moveTimelineBoundary: (oldSourceTimeS, newSourceTimeS) =>
    ipcRenderer.invoke('project:move-boundary', { oldSourceTimeS, newSourceTimeS }),
  updateRenderSettings: (patch) => ipcRenderer.invoke('project:update-render-settings', patch),
  previewEffectsFrame: (sourceTimeS) => ipcRenderer.invoke('project:preview-effects-frame', sourceTimeS),
  addEffectRange: (kind, startS, endS) => ipcRenderer.invoke('project:add-effect-range', { kind, startS, endS }),
  updateEffectRange: (effectId, patch) => ipcRenderer.invoke('project:update-effect-range', { effectId, patch }),
  deleteEffectRange: (effectId) => ipcRenderer.invoke('project:delete-effect-range', effectId),
  importSlideSource: (sourcePath) => ipcRenderer.invoke('project:import-slide-source', sourcePath),
  removeSlideSource: () => ipcRenderer.invoke('project:remove-slide-source'),
  recommendSlides: () => ipcRenderer.invoke('project:recommend-slides'),
  acceptSlideRecommendations: () => ipcRenderer.invoke('project:accept-slide-recommendations'),
  updateSlidePage: (pageId, patch) => ipcRenderer.invoke('project:update-slide-page', { pageId, patch }),
  undoTimeline: () => ipcRenderer.invoke('project:undo'),
  redoTimeline: () => ipcRenderer.invoke('project:redo'),
  saveProject: (saveAs) => ipcRenderer.invoke('project:save', saveAs),
  closeProject: () => ipcRenderer.invoke('project:close'),
  pickPath: (kind) => ipcRenderer.invoke('dialog:pick-path', kind),
  pickBatchFiles: (kind) => ipcRenderer.invoke('dialog:pick-batch-files', kind),
  startAnalysis: (request) => ipcRenderer.invoke('job:start-analysis', request),
  startRender: () => ipcRenderer.invoke('job:start-render'),
  startBatch: (request) => ipcRenderer.invoke('job:start-batch', request),
  cancelJob: (jobId) => ipcRenderer.invoke('job:cancel', jobId),
  onJobEvent: (callback) => {
    ipcRenderer.removeAllListeners('job:event')
    ipcRenderer.on('job:event', (_event, payload) => callback(payload))
  },
  recentProjects: () => ipcRenderer.invoke('recent:list'),
  recoveryInfo: () => ipcRenderer.invoke('recovery:info'),
  restoreRecovery: () => ipcRenderer.invoke('recovery:restore')
}

contextBridge.exposeInMainWorld('creacut', api)
