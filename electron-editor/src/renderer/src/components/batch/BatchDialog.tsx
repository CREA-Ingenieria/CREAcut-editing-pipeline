import { useState } from 'react'
import { AlertCircle, FileText, FileVideo2, FolderOpen, LoaderCircle, Play, Trash2 } from 'lucide-react'
import type { BatchRequest } from '../../../../shared/contracts'
import { compactPath } from '../../format'
import { creacutService } from '../../services/creacut-service'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'

interface BatchDialogProps {
  onClose: () => void
  onStart: (request: BatchRequest) => Promise<void>
}

interface FileSelectionProps {
  title: string
  emptyMessage: string
  paths: string[]
  icon: React.ReactNode
  buttonLabel: string
  onPick: () => Promise<void>
  onRemove: (index: number) => void
}

function FileSelection({
  title,
  emptyMessage,
  paths,
  icon,
  buttonLabel,
  onPick,
  onRemove
}: FileSelectionProps): React.JSX.Element {
  return (
    <section className="min-w-0 rounded-md border border-border bg-secondary/35">
      <div className="flex items-center justify-between gap-3 border-b border-border-soft px-3 py-2">
        <div className="flex items-center gap-2 text-primary">
          {icon}
          <strong className="text-[10px]">{title}</strong>
          <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[8px] font-bold">{paths.length}</span>
        </div>
        <Button variant="secondary" size="sm" className="h-7 px-2.5 text-[9px]" onClick={() => void onPick()}>
          {buttonLabel}
        </Button>
      </div>
      <div className="min-h-[126px] max-h-[210px] overflow-y-auto">
        {paths.length === 0 ? (
          <div className="grid min-h-[126px] place-items-center px-4 text-center text-[9px] text-muted-foreground">
            {emptyMessage}
          </div>
        ) : (
          paths.map((path, index) => (
            <div
              className="grid grid-cols-[22px_minmax(0,1fr)_28px] items-center gap-1.5 border-b border-border-soft px-2 py-2"
              key={path}
            >
              <span className="text-center text-[8px] font-bold text-muted-foreground">{index + 1}</span>
              <span className="truncate text-[9px]" title={path}>{compactPath(path)}</span>
              <Button
                variant="icon"
                size="icon"
                className="h-6 w-6"
                aria-label={`Quitar ${path}`}
                onClick={() => onRemove(index)}
              >
                <Trash2 size={13} />
              </Button>
            </div>
          ))
        )}
      </div>
    </section>
  )
}

export function BatchDialog({ onClose, onStart }: BatchDialogProps): React.JSX.Element {
  const [videoPaths, setVideoPaths] = useState<string[]>([])
  const [scriptPaths, setScriptPaths] = useState<string[]>([])
  const [outputDirectory, setOutputDirectory] = useState('')
  const [starting, setStarting] = useState(false)

  const countMismatch = videoPaths.length !== scriptPaths.length
  const ready = videoPaths.length > 0 && !countMismatch && Boolean(outputDirectory) && !starting

  async function chooseFiles(kind: 'videos' | 'scripts'): Promise<void> {
    const selected = await creacutService.pickBatchFiles(kind)
    if (!selected.length) return
    if (kind === 'videos') setVideoPaths(selected)
    else setScriptPaths(selected)
  }

  async function chooseOutput(): Promise<void> {
    const selected = await creacutService.pickPath('directory')
    if (selected) setOutputDirectory(selected)
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <p className="m-0 mb-1 text-[9px] font-extrabold tracking-[.13em] text-primary">ETAPA 8</p>
          <DialogTitle>Identificar y procesar lote</DialogTitle>
        </DialogHeader>

        <p className="-mt-2 text-[11px] leading-relaxed text-muted-foreground">
          Selecciona todos los videos y todos los guiones. CREAcut transcribirá cada video, identificará
          automáticamente su guion y generará una carpeta independiente por proyecto.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <FileSelection
            title="Videos"
            emptyMessage="Selecciona todos los videos que deseas analizar."
            paths={videoPaths}
            icon={<FileVideo2 size={16} />}
            buttonLabel="Elegir videos…"
            onPick={() => chooseFiles('videos')}
            onRemove={(index) => setVideoPaths((current) => current.filter((_, item) => item !== index))}
          />
          <FileSelection
            title="Guiones"
            emptyMessage="Selecciona la misma cantidad de guiones Markdown."
            paths={scriptPaths}
            icon={<FileText size={16} />}
            buttonLabel="Elegir guiones…"
            onPick={() => chooseFiles('scripts')}
            onRemove={(index) => setScriptPaths((current) => current.filter((_, item) => item !== index))}
          />
        </div>

        {videoPaths.length > 0 && scriptPaths.length > 0 && countMismatch && (
          <div className="flex items-center gap-2 rounded-md border border-warning/30 bg-warning/10 p-2.5 text-[10px] text-warning">
            <AlertCircle size={15} className="shrink-0" />
            Debes seleccionar la misma cantidad: hay {videoPaths.length} video(s) y {scriptPaths.length} guion(es).
          </div>
        )}

        <div>
          <label className="mb-1.5 block text-[9px] text-muted-foreground">Carpeta base de salida</label>
          <div className="grid min-h-10 grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 rounded-md border border-border bg-secondary py-1 pl-2.5 pr-1">
            <FolderOpen size={17} className="text-primary" />
            <span className="truncate text-[11px] text-muted-foreground" title={outputDirectory}>
              {outputDirectory ? compactPath(outputDirectory) : 'Sin seleccionar'}
            </span>
            <Button variant="secondary" size="sm" className="h-7 px-2.5 text-[9px]" onClick={() => void chooseOutput()}>
              Elegir…
            </Button>
          </div>
        </div>

        <p className="m-0 text-[9px] leading-relaxed text-muted-foreground">
          La asignación es uno a uno: después de identificar un guion, ese archivo deja de ser candidato
          para los videos restantes. El lote se procesa secuencialmente para no competir por la GPU.
        </p>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            variant="primary"
            disabled={!ready}
            onClick={() => {
              setStarting(true)
              void onStart({ videoPaths, scriptPaths, outputDirectory }).finally(() => setStarting(false))
            }}
          >
            {starting ? <LoaderCircle className="animate-spin-slow" size={17} /> : <Play size={17} />}
            Procesar {videoPaths.length || ''} video{videoPaths.length === 1 ? '' : 's'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
