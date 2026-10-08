import {
  Clapperboard,
  FilePlus2,
  FolderOpen,
  House,
  Layers3,
  PanelBottom,
  PanelLeft,
  PanelRight,
  Save,
  SaveAll
} from 'lucide-react'
import type { ProjectView } from '../../../shared/contracts'
import { compactPath } from '../format'
import type { PanelKey } from '../hooks/usePanelLayout'
import type { ThemeMode } from '../types/editor'
import { Button } from './ui/button'
import { Separator } from './ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { ThemeButton } from './ThemeButton'
import { cn } from '../lib/utils'
import logoDark from '../assets/brand/creacut-logo-dark.png'
import logoLight from '../assets/brand/creacut-logo-light.png'

/**
 * Barra superior del editor.
 *
 * Jerarquía
 * ---------
 *   1. **Exportar** es la única acción `primary`. Es la salida del flujo y la
 *      que el usuario busca.
 *   2. **Guardar** conserva su etiqueta y solo se activa si hay cambios, de
 *      modo que su estado ya informa sin necesidad de leer nada más.
 *   3. El resto (guardar como, nuevo, abrir, lote) es un grupo de iconos con
 *      tooltip: a un clic de distancia, sin competir por la atención.
 *
 * Los tres conmutadores de panel viven aquí y no en una barra de estado
 * propia: una fila más de cromo restaría alto al visor, que es justo lo que
 * este rediseño intenta ganar.
 */
interface EditorTopbarProps {
  className?: string
  project: ProjectView
  busy: boolean
  theme: ThemeMode
  collapsed: Record<PanelKey, boolean>
  onTogglePanel: (key: PanelKey) => void
  onToggleTheme: () => void
  onSave: (saveAs: boolean) => void
  onNewProject: () => void
  onExport: () => void
  onBatch: () => void
  onOpen: () => void
  onExitProject: () => void
}

/** Botón de icono con tooltip: sin etiqueta visible, la ayuda es obligatoria. */
function IconAction({
  label,
  shortcut,
  onClick,
  disabled,
  active,
  children
}: {
  label: string
  shortcut?: string
  onClick: () => void
  disabled?: boolean
  active?: boolean
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="icon"
          size="icon"
          aria-label={label}
          aria-pressed={active === undefined ? undefined : active}
          data-active={active ? 'true' : undefined}
          className="data-[active=true]:border-primary/50 data-[active=true]:text-primary"
          onClick={onClick}
          disabled={disabled}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {label}
        {shortcut && <span className="ml-2 text-muted-foreground">{shortcut}</span>}
      </TooltipContent>
    </Tooltip>
  )
}

export function EditorTopbar({
  className,
  project,
  busy,
  theme,
  collapsed,
  onTogglePanel,
  onToggleTheme,
  onSave,
  onNewProject,
  onExport,
  onBatch,
  onOpen,
  onExitProject
}: EditorTopbarProps): React.JSX.Element {
  return (
    <header
      className={cn(
        'relative z-10 grid h-12 shrink-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3',
        'border-b border-topbar-border bg-topbar px-3',
        className
      )}
    >
      <div className="flex min-w-0 items-center" title="CREAcut Beta">
        <img
          src={theme === 'light' ? logoLight : logoDark}
          alt="CREA"
          className="h-7 w-auto shrink-0 select-none"
          draggable={false}
        />
        <strong className="translate-y-[3px] text-[15px] font-extrabold uppercase leading-none tracking-tight">
          CUT
        </strong>
        <span className="ml-1.5 translate-y-[3px] rounded border border-warning/40 px-1 py-0.5 text-[7px] font-bold uppercase tracking-[.14em] text-warning">
          Beta
        </span>
      </div>

      <div className="flex min-w-0 items-baseline justify-center gap-2">
        <strong className="truncate text-[12px]">{project.projectName}</strong>
        {project.dirty && (
          <span className="flex shrink-0 items-center gap-1.5 text-[10px] font-semibold text-warning">
            <span className="live-dot" style={{ background: 'var(--warning)' }} />
            <span className="hidden lg:inline">Sin guardar</span>
          </span>
        )}
        <span className="hidden min-w-0 truncate text-[10px] text-muted-foreground xl:inline" title={project.projectPath}>
          {compactPath(project.projectPath)}
        </span>
      </div>

      <div className="flex items-center justify-self-end gap-1.5">
        <IconAction label="Volver al inicio" onClick={onExitProject} disabled={busy}>
          <House size={15} />
        </IconAction>

        <Separator orientation="vertical" className="mx-0.5 h-5" />

        <Button variant="secondary" size="sm" onClick={() => onSave(false)} disabled={busy || !project.dirty} title="Guardar (Ctrl+S)">
          <Save size={14} /> <span className="hidden lg:inline">Guardar</span>
        </Button>

        <IconAction label="Guardar como…" shortcut="Ctrl+Shift+S" onClick={() => onSave(true)} disabled={busy}>
          <SaveAll size={15} />
        </IconAction>
        <IconAction label="Nuevo proyecto" onClick={onNewProject}>
          <FilePlus2 size={15} />
        </IconAction>
        <IconAction label="Abrir proyecto" shortcut="Ctrl+O" onClick={onOpen}>
          <FolderOpen size={15} />
        </IconAction>
        <IconAction label="Procesar lote" onClick={onBatch}>
          <Layers3 size={15} />
        </IconAction>

        <Separator orientation="vertical" className="mx-0.5 h-5" />

        <Button variant="primary" size="sm" onClick={onExport} title="Exportar (Ctrl+E)">
          <Clapperboard size={14} /> Exportar
        </Button>

        <Separator orientation="vertical" className="mx-0.5 h-5" />

        <IconAction label="Panel de material" shortcut="Ctrl+B" active={!collapsed.left} onClick={() => onTogglePanel('left')}>
          <PanelLeft size={15} />
        </IconAction>
        <IconAction label="Línea de tiempo" shortcut="Ctrl+J" active={!collapsed.timeline} onClick={() => onTogglePanel('timeline')}>
          <PanelBottom size={15} />
        </IconAction>
        <IconAction label="Inspector" shortcut="Ctrl+Alt+B" active={!collapsed.right} onClick={() => onTogglePanel('right')}>
          <PanelRight size={15} />
        </IconAction>

        <ThemeButton theme={theme} onToggle={onToggleTheme} />
      </div>
    </header>
  )
}
