import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

/**
 * Botón base.
 *
 * Movimiento
 * ----------
 * Un botón se pulsa decenas de veces al día, así que la única animación que se
 * permite es la respuesta al toque: `scale(.97)` durante 130ms al mantener
 * pulsado. Es la confirmación de que la interfaz ha oído al usuario, y a esa
 * escala se percibe sin llegar a leerse como una animación.
 *
 * Lo que NO hace:
 * - no crece al pasar el ratón (a esta frecuencia acabaría cansando y, con la
 *   barra superior llena de botones, provocaría un baile constante);
 * - no usa `transition: all`, que animaría también sombras y bordes y obliga al
 *   navegador a comprobar cada propiedad en cada fotograma.
 *
 * Las propiedades animadas se nombran una a una y son solo compuestas
 * (`transform`) o baratas (color, sombra).
 */
const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-xs font-semibold outline-none',
    'transition-[background-color,border-color,color,box-shadow,transform,filter] duration-[var(--dur-hover)] ease-out',
    'active:scale-[.97] active:duration-[var(--dur-press)]',
    'disabled:pointer-events-none disabled:opacity-50 disabled:active:scale-100',
    'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    '[&_svg]:pointer-events-none [&_svg]:shrink-0'
  ].join(' '),
  {
    variants: {
      variant: {
        // La acción principal es la única que se ilumina: el halo crece al
        // pasar el ratón para que en una barra llena de botones quede claro
        // cuál es la salida del flujo.
        primary:
          'bg-primary text-primary-foreground shadow-[0_0_0_0_var(--glow-accent)] hover:brightness-110 hover:shadow-[0_0_16px_-2px_var(--glow-accent)]',
        secondary: 'bg-secondary text-secondary-foreground border border-border hover:bg-muted hover:border-primary/40',
        outline: 'border border-border bg-transparent text-foreground hover:bg-muted hover:border-primary/40',
        ghost: 'text-muted-foreground hover:text-foreground hover:bg-muted',
        destructive: 'bg-destructive/10 text-destructive border border-destructive/30 hover:bg-destructive/15',
        icon: 'border border-border bg-secondary text-muted-foreground hover:text-foreground hover:bg-muted hover:border-primary/40'
      },
      size: {
        default: 'h-9 px-3.5',
        sm: 'h-8 px-2.5 text-[11px]',
        lg: 'h-10 px-5 text-sm',
        icon: 'h-8 w-8 shrink-0 rounded-md p-0',
        'icon-lg': 'h-9 w-9 shrink-0 rounded-md p-0'
      }
    },
    defaultVariants: {
      variant: 'secondary',
      size: 'default'
    }
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  }
)
Button.displayName = 'Button'

export { buttonVariants }
