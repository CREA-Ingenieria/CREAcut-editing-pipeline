import type { LucideIcon } from 'lucide-react'
import { cn } from '../lib/utils'

/**
 * Bloque temático del inspector.
 *
 * Antes cada sección repetía a mano su cabecera y todas quedaban con el mismo
 * peso visual, así que el panel se leía como una lista larga sin escalones. Al
 * centralizarla, el título gana un grado sobre el cuerpo (12px frente a 11px) y
 * la separación entre secciones deja de depender de quién escribió cada una.
 */
interface InspectorSectionProps {
  icon: LucideIcon
  title: string
  description?: string
  /** Distintivo opcional a la derecha del título (estado, alcance…). */
  aside?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export function InspectorSection({
  icon: Icon,
  title,
  description,
  aside,
  children,
  className
}: InspectorSectionProps): React.JSX.Element {
  return (
    <section className={cn('flex flex-col gap-2.5', className)}>
      <header className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Icon size={15} className="shrink-0 text-primary" />
          <h3 className="m-0 flex-1 text-xs font-semibold tracking-[-.01em] text-foreground">{title}</h3>
          {aside}
        </div>
        {description && (
          <p className="m-0 text-[11px] leading-relaxed text-muted-foreground">{description}</p>
        )}
      </header>
      {children}
    </section>
  )
}
