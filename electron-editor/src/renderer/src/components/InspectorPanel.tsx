import { useEffect, useState } from 'react'
import type {
  EditSegment,
  ProjectRenderSettingsPatch,
  ProjectView,
  SlidePage,
  VisualEffectKind,
  VisualEffectRange
} from '../../../shared/contracts'
import { ProjectInspector } from './inspector/ProjectInspector'
import { EffectProperties, SlideProperties } from './inspector/SelectionInspector'
import { SlidesLibrary } from './SlidesLibrary'
import { TakeInspectorTab } from './TakeInspectorTab'
import { ScrollArea } from './ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs'
import { cn } from '../lib/utils'

/** Panel derecho: ajustes del proyecto y biblioteca de diapositivas. */
interface InspectorPanelProps {
  className?: string
  style?: React.CSSProperties
  project: ProjectView
  selectedSegment: EditSegment | null
  selectedSegmentId: string | null
  busy: boolean
  onSelectSegment: (segmentId: string) => void
  onSeekCandidate: (timeS: number) => void
  onSelectCandidate: (segmentId: string, candidateId: string) => void
  onRestoreCandidate: (segmentId: string) => void
  onUpdateRenderSettings: (patch: ProjectRenderSettingsPatch) => void
  onPickBackground: () => void
  onPreviewEffects: () => void
  selectedSlideId: string | null
  onUpdateSlidePage: (
    pageId: string,
    patch: Partial<Pick<SlidePage, 'startS' | 'endS' | 'enabled' | 'x' | 'y' | 'speakerWidth' | 'heightFraction'>>
  ) => void
  selectedEffectId: string | null
  sourceTimeS: number
  onAddEffect: (kind: VisualEffectKind) => void
  onSelectEffect: (effectId: string) => void
  onUpdateEffect: (effectId: string, patch: Partial<Pick<VisualEffectRange, 'kind' | 'startS' | 'endS'>>) => void
  onDeleteEffect: (effectId: string) => void
  onSelectSlide: (slideId: string) => void
  onPickSlides: () => void
  onPickSlidesFolder: () => void
  onRemoveSlides: () => void
  onRecommendSlides: () => void
  onAcceptSlideRecommendations: () => void
  onAddSlideToTimeline: (pageId: string) => void
}

type InspectorTab = 'project' | 'slides'

export function InspectorPanel(props: InspectorPanelProps): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<InspectorTab>('project')
  const selectedSlide = props.project.slides?.pages.find((page) => page.id === props.selectedSlideId) ?? null
  const selectedEffect = props.project.effectRanges.find((item) => item.id === props.selectedEffectId) ?? null

  useEffect(() => {
    if (props.selectedSlideId) setActiveTab('slides')
    else if (props.selectedEffectId) setActiveTab('project')
  }, [props.selectedSlideId, props.selectedEffectId])

  return (
    <aside style={props.style} className={cn('flex min-h-0 flex-col overflow-hidden bg-card', props.className)}>
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as InspectorTab)} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="h-9 shrink-0 gap-0 px-1.5">
          <TabsTrigger value="project">Proyecto</TabsTrigger>
          <TabsTrigger value="slides">Diapositivas</TabsTrigger>
        </TabsList>
        <TabsContent value="project" className="min-h-0 flex-1">
          <ProjectInspector
            settings={props.project.renderSettings}
            busy={props.busy}
            onUpdate={props.onUpdateRenderSettings}
            onPickBackground={props.onPickBackground}
            onPreviewEffects={props.onPreviewEffects}
            effectRanges={props.project.effectRanges}
            selectedEffectId={props.selectedEffectId}
            sourceTimeS={props.sourceTimeS}
            onAddEffect={props.onAddEffect}
            onSelectEffect={props.onSelectEffect}
            effectEditor={selectedEffect && (
              <EffectProperties effect={selectedEffect} busy={props.busy} onUpdateEffect={props.onUpdateEffect} onDeleteEffect={props.onDeleteEffect} />
            )}
          >
            <TakeInspectorTab
              project={props.project}
              selectedSegment={props.selectedSegment}
              selectedSegmentId={props.selectedSegmentId}
              busy={props.busy}
              onSelectSegment={props.onSelectSegment}
              onSeekCandidate={props.onSeekCandidate}
              onSelectCandidate={props.onSelectCandidate}
              onRestoreCandidate={props.onRestoreCandidate}
            />
          </ProjectInspector>
        </TabsContent>
        <TabsContent value="slides" className="min-h-0 flex-1">
          <div className="flex h-full min-h-0 flex-col">
            <div className="min-h-0 flex-1">
              <SlidesLibrary
                slides={props.project.slides}
                busy={props.busy}
                selectedSlideId={props.selectedSlideId}
                onSelectSlide={props.onSelectSlide}
                onPickSlides={props.onPickSlides}
                onPickSlidesFolder={props.onPickSlidesFolder}
                onRemoveSlides={props.onRemoveSlides}
                onRecommendSlides={props.onRecommendSlides}
                onAcceptSlideRecommendations={props.onAcceptSlideRecommendations}
                onUpdateSlidePage={props.onUpdateSlidePage}
                onAddSlideToTimeline={props.onAddSlideToTimeline}
              />
            </div>
            {selectedSlide && (
              <ScrollArea className="h-1/2 shrink-0 border-t border-border">
                <div className="flex flex-col gap-4 px-3.5 pb-6 pt-3.5">
                  <strong className="text-xs">Diapositiva {selectedSlide.index + 1}</strong>
                  <SlideProperties
                    page={selectedSlide}
                    chromaEnabled={props.project.renderSettings.chromaEnabled}
                    busy={props.busy}
                    onUpdateSlidePage={props.onUpdateSlidePage}
                    onPreviewEffects={props.onPreviewEffects}
                  />
                </div>
              </ScrollArea>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </aside>
  )
}
