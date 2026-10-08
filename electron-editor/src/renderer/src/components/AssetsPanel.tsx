import { useEffect, useRef } from 'react'
import type { ProjectView } from '../../../shared/contracts'
import { formatTime } from '../format'
import { cn } from '../lib/utils'
import type { LeftTab } from '../types/editor'
import { ScriptPanel } from './ScriptPanel'
import { ScrollArea } from './ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs'

/** Panel izquierdo: transcripción y guion del proyecto. */
interface AssetsPanelProps {
  className?: string
  style?: React.CSSProperties
  project: ProjectView
  activeTranscriptIndex: number | null
  activeScriptSegmentId: string | null
  selectedSegmentId: string | null
  tab: LeftTab
  onTabChange: (tab: LeftTab) => void
  onSelectTranscript: (index: number) => void
  onSelectSegment: (segmentId: string) => void
}

export function AssetsPanel({
  className,
  style,
  project,
  activeTranscriptIndex,
  activeScriptSegmentId,
  selectedSegmentId,
  tab,
  onTabChange,
  onSelectTranscript,
  onSelectSegment,
}: AssetsPanelProps): React.JSX.Element {
  const activeTranscriptRef = useRef<HTMLButtonElement>(null)
  const segments = project.project.transcript.segments

  useEffect(() => {
    if (tab !== 'transcript' || activeTranscriptIndex === null) return
    const frame = window.requestAnimationFrame(() => {
      activeTranscriptRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [activeTranscriptIndex, tab])

  return (
    <aside style={style} className={cn('flex min-h-0 flex-col overflow-hidden bg-card', className)}>
      <Tabs value={tab} onValueChange={(value) => onTabChange(value as LeftTab)} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="h-9 shrink-0 gap-0 px-1.5">
          <TabsTrigger value="transcript">Transcripción</TabsTrigger>
          <TabsTrigger value="script">Guion</TabsTrigger>
        </TabsList>

        <TabsContent value="transcript" className="min-h-0 flex-1">
          {segments.length === 0 ? (
            <p className="p-4 text-[11px] leading-relaxed text-muted-foreground">
              El proyecto no tiene transcripción. Vuelve a analizarlo para generarla.
            </p>
          ) : (
            <ScrollArea className="h-full">
              <div className="flex flex-col p-1">
                {segments.map((item, index) => {
                  const active = activeTranscriptIndex === index
                  return (
                    <button
                      key={`${item.start}-${index}`}
                      ref={active ? activeTranscriptRef : undefined}
                      type="button"
                      aria-current={active ? 'true' : undefined}
                      className={cn(
                        'group relative grid grid-cols-[42px_1fr] gap-2 rounded-md border border-transparent px-2 py-1.5 text-left',
                        // Navegar por la transcripcion es una accion de decenas
                        // de veces por sesion: la transicion tiene que ser casi
                        // imperceptible y nunca desplazar el texto.
                        'transition-colors duration-[var(--dur-hover)] ease-out hover:bg-secondary',
                        // Barra lateral que crece desde el centro. Es un
                        // `scaleY`, no una altura: no provoca reflow de la lista.
                        'before:absolute before:inset-y-1 before:left-0 before:w-[2px] before:rounded-full before:bg-primary',
                        'before:origin-center before:scale-y-0 before:transition-transform before:duration-[var(--dur-pop)] before:ease-out',
                        active && 'border-brand-strong/25 bg-brand-soft before:scale-y-100'
                      )}
                      onClick={() => onSelectTranscript(index)}
                    >
                      <span className={cn('pt-px font-mono text-[10px] tabular-nums text-muted-foreground/80', active && 'text-brand')}>
                        {formatTime(item.start)}
                      </span>
                      <p className="m-0 text-[11px] leading-relaxed text-foreground/85">
                        {item.text.trim() || 'Segmento sin texto'}
                      </p>
                    </button>
                  )
                })}
              </div>
            </ScrollArea>
          )}
        </TabsContent>

        <TabsContent value="script" className="min-h-0 flex-1">
          <ScriptPanel
            segments={project.project.segments}
            scriptText={project.scriptText}
            scriptError={project.scriptError}
            activeSegmentId={activeScriptSegmentId}
            selectedSegmentId={selectedSegmentId}
            visible={tab === 'script'}
            onSelectSegment={onSelectSegment}
          />
        </TabsContent>
      </Tabs>
    </aside>
  )
}
