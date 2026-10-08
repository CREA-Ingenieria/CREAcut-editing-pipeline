import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  FileCog,
  FileImage,
  FileText,
  FileVideo2,
  FolderOpen,
  LoaderCircle,
  Plus,
  X
} from 'lucide-react'
import type {
  AnalysisRequest,
  DeviceStatus,
  JobEvent
} from '../../shared/contracts'
import { compactPath } from './format'
import { cn } from './lib/utils'
import { creacutService } from './services/creacut-service'
import { Button } from './components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from './components/ui/dialog'

interface CreateDialogProps {
  onClose: () => void
  onStart: (request: AnalysisRequest) => Promise<void>
}

interface PathFieldProps {
  label: string
  value: string
  optional?: boolean
  icon: React.ReactNode
  onPick: () => Promise<void>
  onClear?: () => void
}

function PathField({ label, value, optional, icon, onPick, onClear }: PathFieldProps): React.JSX.Element {
  return (
    <div>
      <label className="mb-1.5 flex justify-between text-[9px] text-muted-foreground">
        {label}
        {optional && <span className="text-muted-foreground/70">Opcional</span>}
      </label>
      <div className="grid min-h-10 grid-cols-[24px_minmax(0,1fr)_auto_auto] items-center gap-2 rounded-md border border-border bg-secondary py-1 pl-2.5 pr-1">
        <span className="grid place-items-center text-primary">{icon}</span>
        <span className="truncate text-[11px] text-muted-foreground" title={value}>
          {value ? compactPath(value) : 'Sin seleccionar'}
        </span>
        {value && onClear && (
          <Button variant="icon" size="icon" className="h-6 w-6" onClick={onClear}>
            <X size={14} />
          </Button>
        )}
        <Button variant="secondary" size="sm" className="h-7 px-2.5 text-[9px]" onClick={() => void onPick()}>
          Elegir…
        </Button>
      </div>
    </div>
  )
}

export function CreateProjectDialog({ onClose, onStart }: CreateDialogProps): React.JSX.Element {
  const [videoPath, setVideoPath] = useState('')
  const [scriptPath, setScriptPath] = useState('')
  const [projectPath, setProjectPath] = useState('')
  const [configPath, setConfigPath] = useState('')
  const [backgroundImage, setBackgroundImage] = useState('')
  const [device, setDevice] = useState<DeviceStatus | null>(null)
  const [deviceError, setDeviceError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    creacutService.deviceStatus().then(setDevice).catch((reason: unknown) => {
      setDeviceError(reason instanceof Error ? reason.message : String(reason))
    })
  }, [])

  async function choose(kind: 'video' | 'script' | 'config' | 'image' | 'project-output'): Promise<void> {
    const selected = await creacutService.pickPath(kind)
    if (!selected) return
    if (kind === 'video') setVideoPath(selected)
    else if (kind === 'script') setScriptPath(selected)
    else if (kind === 'config') setConfigPath(selected)
    else if (kind === 'image') setBackgroundImage(selected)
    else setProjectPath(selected)
  }

  const ready = videoPath && scriptPath && projectPath && !starting
  const cuda = device?.device === 'cuda'

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <p className="m-0 mb-1 text-[9px] font-extrabold tracking-[.13em] text-primary">ETAPA 6</p>
          <DialogTitle>Crear proyecto editable</DialogTitle>
        </DialogHeader>

        <p className="-mt-2 text-[11px] leading-relaxed text-muted-foreground">
          CREAcut ejecutará Whisper y la alineación, pero no renderizará el MP4 final.
        </p>

        <div
          className={cn(
            'flex items-center gap-2.5 rounded-md border p-2.5',
            cuda ? 'border-brand-strong/30 text-primary' : 'border-warning/30 text-warning'
          )}
        >
          <Cpu size={20} className="shrink-0" />
          <div className="flex flex-col gap-0.5">
            <strong className="text-[11px]">
              {device ? device.label : deviceError ? 'No se pudo consultar el dispositivo' : 'Consultando dispositivo…'}
            </strong>
            <span className="text-[9px] text-muted-foreground">
              {cuda
                ? 'Whisper utilizará la GPU NVIDIA y FP16.'
                : device
                  ? 'Whisper utilizará CPU y FP32; no se ocultará este cambio.'
                  : (deviceError ?? 'Preparando diagnóstico local.')}
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-2.5">
          <PathField label="Video fuente" value={videoPath} icon={<FileVideo2 size={17} />} onPick={() => choose('video')} />
          <PathField label="Guion Markdown" value={scriptPath} icon={<FileText size={17} />} onPick={() => choose('script')} />
          <PathField label="Proyecto de salida" value={projectPath} icon={<FolderOpen size={17} />} onPick={() => choose('project-output')} />
          <PathField label="Configuración YAML" optional value={configPath} icon={<FileCog size={17} />} onPick={() => choose('config')} onClear={() => setConfigPath('')} />
          <PathField label="Fondo para chroma" optional value={backgroundImage} icon={<FileImage size={17} />} onPick={() => choose('image')} onClear={() => setBackgroundImage('')} />
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            variant="primary"
            disabled={!ready}
            onClick={() => {
              setStarting(true)
              void onStart({ videoPath, scriptPath, projectPath, configPath, backgroundImage }).finally(() => setStarting(false))
            }}
          >
            {starting ? <LoaderCircle className="animate-spin-slow" size={17} /> : <Plus size={17} />}
            Iniciar análisis
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface JobDialogProps {
  event: JobEvent
  logs: string[]
  onClose: () => void
  onCancel: () => Promise<void>
  onOpenProject?: (path: string) => Promise<void>
}

export function JobDialog({ event, logs, onClose, onCancel, onOpenProject }: JobDialogProps): React.JSX.Element {
  const logRef = useRef<HTMLDivElement>(null)
  const terminal = ['completed', 'failed', 'cancelled'].includes(event.kind)

  // El registro crece durante toda la operación y lo interesante es siempre
  // lo último: sin esto había que desplazarlo a mano en cada línea nueva para
  // saber por dónde iba Whisper.
  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [logs.length])
  const title = event.jobKind === 'analysis' ? 'Analizando proyecto' : event.jobKind === 'render' ? 'Exportando MP4' : 'Procesando lote'

  return (
    <Dialog open onOpenChange={(open) => !open && terminal && onClose()}>
      <DialogContent
        size="lg"
        onEscapeKeyDown={(e) => !terminal && e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <div className="flex items-center gap-3.5">
          {event.kind === 'completed' ? (
            <CheckCircle2 size={36} className="shrink-0 text-primary" />
          ) : event.kind === 'failed' ? (
            <AlertCircle size={36} className="shrink-0 text-destructive" />
          ) : (
            <LoaderCircle className={cn('shrink-0 text-primary', !terminal && 'animate-spin-slow')} size={36} />
          )}
          <div>
            <p className="m-0 mb-1 text-[9px] font-extrabold tracking-[.13em] text-primary">{event.jobKind.toUpperCase()}</p>
            <DialogTitle>
              {event.kind === 'completed'
                ? 'Operación completada'
                : event.kind === 'failed'
                  ? 'La operación falló'
                  : event.kind === 'cancelled'
                    ? 'Operación cancelada'
                    : title}
            </DialogTitle>
            {event.label && (
              <span className="mt-1.5 inline-flex items-center gap-1 text-[9px] text-muted-foreground">
                <Cpu size={13} /> {event.label}
              </span>
            )}
          </div>
        </div>

        {event.error && (
          <div className="flex gap-1.5 rounded-md bg-destructive/10 p-2.5 text-[10px] text-destructive">
            <AlertCircle size={16} className="shrink-0" /> {event.error}
          </div>
        )}

        <div ref={logRef} className="h-[250px] overflow-y-auto rounded-md border border-border bg-background p-2.5 font-mono text-[10px] leading-relaxed text-muted-foreground">
          {logs.length ? logs.map((line, index) => <div key={`${index}-${line}`}>{line}</div>) : <div>Preparando operación…</div>}
        </div>

        {event.jobKind === 'batch' && event.kind === 'completed' && (
          <div className="mt-2">
            <div className="flex justify-between text-[10px] text-primary">
              <strong>{event.result?.generatedProjects?.length ?? 0} proyectos generados</strong>
              <span>{event.result?.failed?.length ?? 0} elementos con error</span>
            </div>
            <div className="mt-2">
              {event.result?.matches?.map((match) => (
                <button
                  key={match.projectPath}
                  className="grid w-full grid-cols-[18px_minmax(0,1fr)_auto] items-center gap-1.5 border-0 border-t border-border-soft bg-transparent px-1 py-2 text-left text-muted-foreground transition-colors hover:text-primary"
                  onClick={() => void onOpenProject?.(match.projectPath)}
                >
                  <FolderOpen size={14} />
                  <span className="min-w-0">
                    <strong className="block truncate text-[9px]">{compactPath(match.videoPath)}</strong>
                    <span className="block truncate text-[8px]">→ {compactPath(match.scriptPath)}</span>
                  </span>
                  <span className="text-[9px] font-bold text-primary">
                    {match.score === null ? '—' : `${Math.round(match.score * 100)}%`}
                  </span>
                </button>
              ))}
              {!event.result?.matches?.length && event.result?.generatedProjects?.map((path) => (
                <button
                  key={path}
                  className="flex w-full items-center gap-1.5 border-0 border-t border-border-soft bg-transparent px-1 py-2 text-left text-muted-foreground transition-colors hover:text-primary"
                  onClick={() => void onOpenProject?.(path)}
                >
                  <FolderOpen size={14} /> <span>{compactPath(path)}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <DialogFooter>
          {terminal ? (
            <Button variant="primary" onClick={onClose}>Cerrar</Button>
          ) : (
            <Button variant="destructive" onClick={() => void onCancel()}>Cancelar operación</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
