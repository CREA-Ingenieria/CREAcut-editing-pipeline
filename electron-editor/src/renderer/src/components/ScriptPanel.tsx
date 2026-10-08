import { useEffect, useMemo, useRef } from 'react'
import type { EditSegment } from '../../../shared/contracts'
import { cn } from '../lib/utils'
import { ScrollArea } from './ui/scroll-area'

interface ScriptPanelProps {
  segments: EditSegment[]
  scriptText: string | null
  scriptError: string | null
  activeSegmentId: string | null
  selectedSegmentId: string | null
  visible: boolean
  onSelectSegment: (segmentId: string) => void
}

interface ScriptParagraph {
  paragraphIndex: number
  segments: EditSegment[]
}

export function ScriptPanel({
  segments,
  scriptText,
  scriptError,
  activeSegmentId,
  selectedSegmentId,
  visible,
  onSelectSegment
}: ScriptPanelProps): React.JSX.Element {
  const activeItemRef = useRef<HTMLButtonElement>(null)
  const paragraphs = useMemo<ScriptParagraph[]>(() => {
    const grouped = new Map<number, EditSegment[]>()
    for (const segment of segments) {
      const paragraph = grouped.get(segment.paragraph_idx) ?? []
      paragraph.push(segment)
      grouped.set(segment.paragraph_idx, paragraph)
    }
    return [...grouped.entries()]
      .sort(([left], [right]) => left - right)
      .map(([paragraphIndex, paragraphSegments]) => ({
        paragraphIndex,
        segments: [...paragraphSegments].sort(
          (left, right) => left.sentence_idx - right.sentence_idx
        )
      }))
  }, [segments])

  useEffect(() => {
    if (!visible || !activeSegmentId) return
    const frame = window.requestAnimationFrame(() => {
      activeItemRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [activeSegmentId, visible])

  return (
    <ScrollArea className="h-full">
      {paragraphs.length > 0 ? (
        <div className="flex flex-col gap-3 p-2.5">
          {paragraphs.map((paragraph) => (
            <section key={paragraph.paragraphIndex} className="flex flex-col gap-1">
              <p className="m-0 px-2.5 pb-0.5 text-[9px] font-bold tracking-[.12em] text-muted-foreground">
                PÁRRAFO {paragraph.paragraphIndex + 1}
              </p>
              {paragraph.segments.map((segment) => {
                const active = segment.id === activeSegmentId
                const selected = segment.id === selectedSegmentId
                return (
                  <button
                    key={segment.id}
                    ref={active ? activeItemRef : undefined}
                    type="button"
                    aria-current={active ? 'true' : undefined}
                    className={cn(
                      'grid grid-cols-[32px_1fr] gap-2 rounded-md border border-transparent px-2.5 py-2 text-left transition-colors hover:bg-secondary',
                      selected && !active && 'border-border bg-secondary/45',
                      active && 'border-brand-strong/30 bg-brand-soft'
                    )}
                    onClick={() => onSelectSegment(segment.id)}
                  >
                    <span
                      className={cn(
                        'pt-0.5 font-mono text-[10px] tabular-nums text-muted-foreground/80',
                        active && 'font-bold text-brand'
                      )}
                    >
                      {segment.sentence_idx + 1}
                    </span>
                    <p className="m-0 text-xs leading-relaxed text-foreground/85">
                      {segment.script_text}
                    </p>
                  </button>
                )
              })}
            </section>
          ))}
        </div>
      ) : scriptText ? (
        <pre className="whitespace-pre-wrap p-3 font-sans text-xs leading-relaxed text-foreground/85">
          {scriptText}
        </pre>
      ) : (
        <p className="p-3 text-xs leading-relaxed text-muted-foreground">
          {scriptError ?? 'Guion no disponible'}
        </p>
      )}
    </ScrollArea>
  )
}
