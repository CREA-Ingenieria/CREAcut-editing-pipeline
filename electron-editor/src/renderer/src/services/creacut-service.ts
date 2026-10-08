import type { CreacutApi } from '../../../shared/contracts'

/**
 * Facade over the preload API. Views and components never access window.creacut
 * directly; this is the renderer's only gateway to the Electron main process.
 */
export const creacutService: CreacutApi = {
  backendSetupStatus: () => window.creacut.backendSetupStatus(),
  startBackendSetup: () => window.creacut.startBackendSetup(),
  onBackendSetupProgress: (callback) => window.creacut.onBackendSetupProgress(callback),
  bridgeStatus: () => window.creacut.bridgeStatus(),
  deviceStatus: () => window.creacut.deviceStatus(),
  openProject: () => window.creacut.openProject(),
  openProjectPath: (path) => window.creacut.openProjectPath(path),
  locateMedia: () => window.creacut.locateMedia(),
  loadTimelineMedia: (sampleCount, waveformBuckets) =>
    window.creacut.loadTimelineMedia(sampleCount, waveformBuckets),
  selectCandidate: (segmentId, candidateId) =>
    window.creacut.selectCandidate(segmentId, candidateId),
  restoreCandidate: (segmentId) => window.creacut.restoreCandidate(segmentId),
  markRegion: (regionId, keep) => window.creacut.markRegion(regionId, keep),
  restoreRegion: (regionId) => window.creacut.restoreRegion(regionId),
  splitTimeline: (sourceTimeS) => window.creacut.splitTimeline(sourceTimeS),
  moveTimelineBoundary: (oldSourceTimeS, newSourceTimeS) =>
    window.creacut.moveTimelineBoundary(oldSourceTimeS, newSourceTimeS),
  updateRenderSettings: (patch) => window.creacut.updateRenderSettings(patch),
  previewEffectsFrame: (sourceTimeS) => window.creacut.previewEffectsFrame(sourceTimeS),
  addEffectRange: (kind, startS, endS) => window.creacut.addEffectRange(kind, startS, endS),
  updateEffectRange: (effectId, patch) => window.creacut.updateEffectRange(effectId, patch),
  deleteEffectRange: (effectId) => window.creacut.deleteEffectRange(effectId),
  importSlideSource: (sourcePath) => window.creacut.importSlideSource(sourcePath),
  removeSlideSource: () => window.creacut.removeSlideSource(),
  recommendSlides: () => window.creacut.recommendSlides(),
  acceptSlideRecommendations: () => window.creacut.acceptSlideRecommendations(),
  updateSlidePage: (pageId, patch) => window.creacut.updateSlidePage(pageId, patch),
  undoTimeline: () => window.creacut.undoTimeline(),
  redoTimeline: () => window.creacut.redoTimeline(),
  saveProject: (saveAs) => window.creacut.saveProject(saveAs),
  closeProject: () => window.creacut.closeProject(),
  pickPath: (kind) => window.creacut.pickPath(kind),
  pickBatchFiles: (kind) => window.creacut.pickBatchFiles(kind),
  startAnalysis: (request) => window.creacut.startAnalysis(request),
  startRender: () => window.creacut.startRender(),
  startBatch: (request) => window.creacut.startBatch(request),
  cancelJob: (jobId) => window.creacut.cancelJob(jobId),
  onJobEvent: (callback) => window.creacut.onJobEvent(callback),
  recentProjects: () => window.creacut.recentProjects(),
  recoveryInfo: () => window.creacut.recoveryInfo(),
  restoreRecovery: () => window.creacut.restoreRecovery()
}
