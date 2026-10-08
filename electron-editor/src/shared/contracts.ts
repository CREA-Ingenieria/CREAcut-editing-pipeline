import type { BackendSetupStatus } from './backend-setup'
export type { BackendSetupProgress, BackendSetupStatus, BackendSetupStep, BackendSetupStepId, BackendSetupStepState } from './backend-setup'

export interface BridgeStatus {
  protocolVersion: number
  backendVersion: string
  pythonVersion: string
  pythonExecutable: string
  platform: string
}

export interface DeviceStatus {
  device: 'cuda' | 'cpu' | string
  label: string
  fp16: boolean
}

export interface TimelineRegion {
  id: string
  startS: number
  endS: number
  automaticKeep: boolean
  keep: boolean
  origin: string
  linkedSegmentIds: string[]
}

export interface PreviewClip {
  index: number
  sourceStartS: number
  sourceEndS: number
  editStartS: number
  editEndS: number
}

export interface Candidate {
  id: string
  source_start_s: number
  source_end_s: number
  duration_s: number
  score: number
  transcript_text: string
  segment_start_idx?: number | null
  segment_end_idx?: number | null
  refinements: string[]
}

export interface EditSegment {
  id: string
  paragraph_idx: number
  sentence_idx: number
  script_text: string
  candidates: Candidate[]
  selected_candidate_id: string | null
  source_start_s: number | null
  source_end_s: number | null
  automatic_selection: {
    recommended_candidate_id: string | null
    selection_reason: string
  }
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  words?: Array<{ start: number; end: number; word: string }>
}

export interface ProjectRenderSettings {
  transitionType: 'cut' | 'dissolve' | 'fade_black' | 'wipe_left' | 'slide_left'
  crossfadeS: number
  chromaEnabled: boolean
  backgroundImage: string | null
  skinCorrectionEnabled: boolean
  skinCorrectionStrength: number
  listOverlaysEnabled: boolean
  termOverlaysEnabled: boolean
  boldCardsEnabled: boolean
  normalizeAudio: boolean
}

export type ProjectRenderSettingsPatch = Partial<ProjectRenderSettings>

export interface EffectFramePreview {
  url: string
  presenterUrl: string | null
  timeS: number
  slidePageId: string | null
}

export type VisualEffectKind =
  | 'cinematic'
  | 'warm'
  | 'cool'
  | 'black_white'
  | 'vintage'
  | 'vivid'

export interface VisualEffectRange {
  id: string
  kind: VisualEffectKind
  startS: number
  endS: number
}

export interface SlidePage {
  id: string
  index: number
  imagePath: string
  imageUrl: string | null
  thumbnailPath: string
  thumbnailUrl: string | null
  width: number
  height: number
  text: string
  recommendedStartS: number | null
  recommendedEndS: number | null
  recommendationScore: number
  recommendationReason: string
  recommendationMode: 'unscored' | 'lexical-match' | 'ordered-fallback'
  startS: number | null
  endS: number | null
  enabled: boolean
  x: number
  y: number
  speakerWidth: number
  heightFraction: number
  cropX: number
  cropY: number
  cropWidth: number
  cropHeight: number
}

export interface SlideDeck {
  sourcePath: string
  sourceKind: 'pptx' | 'pdf' | 'images'
  renderer: string
  importedAtUtc: string
  pages: SlidePage[]
}

export interface ProjectPayload {
  kind: string
  schema_version: number
  project_id: string
  source: {
    path: string
    duration_s: number | null
  }
  script: {
    path: string
  }
  transcript: {
    text: string
    segments: TranscriptSegment[]
  }
  segments: EditSegment[]
  extensions: Record<string, unknown>
}

export interface ProjectView {
  projectPath: string
  projectName: string
  sourcePath: string | null
  sourceExists: boolean
  mediaUrl: string | null
  scriptText: string | null
  scriptError: string | null
  dirty: boolean
  canUndo: boolean
  canRedo: boolean
  project: ProjectPayload
  timeline: {
    durationS: number
    regions: TimelineRegion[]
    cutPointsS: number[]
  }
  preview: {
    durationS: number
    clips: PreviewClip[]
    cutPointsS: number[]
  }
  renderSettings: ProjectRenderSettings
  effectRanges: VisualEffectRange[]
  slides: SlideDeck | null
}

export interface AnalysisRequest {
  videoPath: string
  scriptPath: string
  projectPath: string
  configPath?: string | null
  backgroundImage?: string | null
}

export interface BatchRequest {
  videoPaths: string[]
  scriptPaths: string[]
  outputDirectory: string
}

export interface BatchMatch {
  videoPath: string
  scriptPath: string
  score: number | null
  projectPath: string
}

export interface JobEvent {
  jobId: string
  jobKind: 'analysis' | 'render' | 'batch'
  kind: 'started' | 'progress' | 'device' | 'completed' | 'failed' | 'cancelled'
  message?: string
  device?: string
  label?: string
  result?: {
    projectPath?: string
    outputPath?: string
    generatedProjects?: string[]
    matches?: BatchMatch[]
    failed?: Array<{ video: string; error: string }>
    unmatchedScripts?: string[]
    projectView?: ProjectView
  }
  error?: string
  detail?: string
  itemIndex?: number
  itemTotal?: number
}

export interface RecentProject {
  path: string
  name: string
  openedAt: string
  previewImages?: Array<{ url: string; label: string }>
}

export interface RecoveryInfo {
  projectPath: string
  projectName: string
  savedAt: string
}

export interface TimelineThumbnail {
  timeS: number
  url: string
}

export interface TimelineMedia {
  thumbnails: TimelineThumbnail[]
  waveform: number[]
  warning: string | null
}

export interface CreacutApi {
  /** Estado de la preparación del primer arranque (siempre `ready` fuera de macOS empaquetado). */
  backendSetupStatus: () => Promise<BackendSetupStatus>
  /** Inicia o reintenta la preparación; si ya corre, devuelve la misma. */
  startBackendSetup: () => Promise<BackendSetupStatus>
  onBackendSetupProgress: (callback: (status: BackendSetupStatus) => void) => void
  bridgeStatus: () => Promise<BridgeStatus>
  deviceStatus: () => Promise<DeviceStatus>
  openProject: () => Promise<ProjectView | null>
  openProjectPath: (path: string) => Promise<ProjectView>
  locateMedia: () => Promise<ProjectView | null>
  loadTimelineMedia: (sampleCount: number, waveformBuckets: number) => Promise<TimelineMedia>
  selectCandidate: (segmentId: string, candidateId: string) => Promise<ProjectView>
  restoreCandidate: (segmentId: string) => Promise<ProjectView>
  markRegion: (regionId: string, keep: boolean) => Promise<ProjectView>
  restoreRegion: (regionId: string) => Promise<ProjectView>
  splitTimeline: (sourceTimeS: number) => Promise<ProjectView>
  moveTimelineBoundary: (oldSourceTimeS: number, newSourceTimeS: number) => Promise<ProjectView>
  updateRenderSettings: (patch: ProjectRenderSettingsPatch) => Promise<ProjectView>
  previewEffectsFrame: (sourceTimeS: number) => Promise<EffectFramePreview>
  addEffectRange: (kind: VisualEffectKind, startS: number, endS: number) => Promise<ProjectView>
  updateEffectRange: (effectId: string, patch: Partial<Pick<VisualEffectRange, 'kind' | 'startS' | 'endS'>>) => Promise<ProjectView>
  deleteEffectRange: (effectId: string) => Promise<ProjectView>
  importSlideSource: (sourcePath: string) => Promise<ProjectView>
  removeSlideSource: () => Promise<ProjectView>
  recommendSlides: () => Promise<ProjectView>
  acceptSlideRecommendations: () => Promise<ProjectView>
  updateSlidePage: (pageId: string, patch: Partial<Pick<SlidePage, 'startS' | 'endS' | 'enabled' | 'x' | 'y' | 'speakerWidth' | 'heightFraction'>>) => Promise<ProjectView>
  undoTimeline: () => Promise<ProjectView>
  redoTimeline: () => Promise<ProjectView>
  saveProject: (saveAs: boolean) => Promise<ProjectView | null>
  closeProject: () => Promise<boolean>
  pickPath: (kind: 'video' | 'script' | 'config' | 'image' | 'slides' | 'project-output' | 'directory') => Promise<string | null>
  pickBatchFiles: (kind: 'videos' | 'scripts') => Promise<string[]>
  startAnalysis: (request: AnalysisRequest) => Promise<string>
  startRender: () => Promise<string | null>
  startBatch: (request: BatchRequest) => Promise<string>
  cancelJob: (jobId: string) => Promise<boolean>
  onJobEvent: (callback: (event: JobEvent) => void) => void
  recentProjects: () => Promise<RecentProject[]>
  recoveryInfo: () => Promise<RecoveryInfo | null>
  restoreRecovery: () => Promise<ProjectView | null>
}
