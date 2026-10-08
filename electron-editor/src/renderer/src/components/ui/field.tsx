import * as React from 'react'
import { cn } from '../../lib/utils'
import { Label } from './label'

/**
 * Primitivos de formulario del inspector.
 *
 * Existen porque el mismo trío «etiqueta + control + nota» estaba repetido a
 * mano en cada ajuste, cada vez con un tamaño de texto y una separación algo
 * distintos. Al no haber una escala tipográfica, el panel había acumulado
 * `text-[9px]`, `text-[10px]` y `text-[11px]` mezclados sin criterio, y 9px es
 * demasiado pequeño para texto corrido en una aplicación de escritorio.
 *
 * La escala que fijan estos componentes:
 *
 *   12px semibold  título de sección
 *   11px medium    etiqueta de un control
 *   11px regular   texto explicativo
 *   10px tabular   cifras y marcas de tiempo
 *    9px uppercase solo para eyebrows en versales, nunca para leer
 */

interface FieldProps {
  label: string
  /** Se enlaza con el `id` del control para que la etiqueta sea accionable. */
  htmlFor?: string
  /** Cifra o estado que acompaña a la etiqueta, alineado a la derecha. */
  readout?: React.ReactNode
  hint?: string
  children: React.ReactNode
  className?: string
}

export function Field({
  label,
  htmlFor,
  readout,
  hint,
  children,
  className
}: FieldProps): React.JSX.Element {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={htmlFor}>{label}</Label>
        {readout !== undefined && (
          <span className="text-[10px] font-semibold tabular-nums text-foreground">{readout}</span>
        )}
      </div>
      {children}
      {hint && <p className="m-0 text-[11px] leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  )
}

interface RangeFieldProps extends Omit<FieldProps, 'children' | 'readout'> {
  value: number
  min: number
  max: number
  step: number
  disabled?: boolean
  /** Texto de la cifra actual; si falta, se muestra el valor crudo. */
  readout?: React.ReactNode
  /** Extremos de la escala, para no obligar a adivinar el rango. */
  minLabel?: string
  maxLabel?: string
  onValueChange: (value: number) => void
}

/**
 * Control continuo para magnitudes continuas.
 *
 * Sustituye a los desplegables de valores fijos que había antes: una duración o
 * una intensidad no son una lista de opciones, y presentarlas así obliga a
 * abrir un menú para comparar dos valores contiguos. Reutiliza la clase
 * `.scrub` del reproductor, así que el gesto es el mismo en toda la aplicación.
 */
export function RangeField({
  value,
  min,
  max,
  step,
  disabled = false,
  readout,
  minLabel,
  maxLabel,
  onValueChange,
  ...fieldProps
}: RangeFieldProps): React.JSX.Element {
  const progress = max > min ? ((value - min) / (max - min)) * 100 : 0

  return (
    <Field {...fieldProps} readout={readout ?? value}>
      <input
        className="scrub w-full"
        style={{ '--scrub-progress': `${progress}%` } as React.CSSProperties}
        type="range"
        id={fieldProps.htmlFor}
        aria-label={fieldProps.label}
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onValueChange(Number(event.target.value))}
      />
      {(minLabel || maxLabel) && (
        <div className="flex justify-between text-[10px] tabular-nums text-muted-foreground">
          <span>{minLabel}</span>
          <span>{maxLabel}</span>
        </div>
      )}
    </Field>
  )
}
