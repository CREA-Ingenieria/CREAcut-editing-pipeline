import type { LucideIcon } from 'lucide-react'
import { cn } from '../lib/utils'

interface SettingToggleProps {
  icon: LucideIcon
  title: string
  description: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}

export function SettingToggle({
  icon: Icon,
  title,
  description,
  checked,
  disabled = false,
  onCheckedChange
}: SettingToggleProps): React.JSX.Element {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className="flex w-full items-center gap-3 rounded-md border border-border bg-secondary px-3 py-2.5 text-left outline-none transition-colors hover:border-muted-foreground/40 disabled:cursor-not-allowed disabled:opacity-50"
      onClick={() => onCheckedChange(!checked)}
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-background text-primary">
        <Icon size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <strong className="block text-[11px] font-semibold text-foreground">{title}</strong>
        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">{description}</span>
      </span>
      <span
        aria-hidden="true"
        className={cn(
          'relative h-5 w-9 shrink-0 rounded-full border border-border bg-background transition-colors',
          checked && 'border-primary bg-primary'
        )}
      >
        <span
          className={cn(
            'absolute left-0.5 top-0.5 h-3.5 w-3.5 rounded-full bg-muted-foreground transition-transform',
            checked && 'translate-x-4 bg-primary-foreground'
          )}
        />
      </span>
    </button>
  )
}
