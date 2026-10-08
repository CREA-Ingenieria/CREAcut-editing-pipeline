import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogPortal = DialogPrimitive.Portal
export const DialogClose = DialogPrimitive.Close

export const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      // Radix retrasa el desmontaje mientras haya una animacion en curso, asi
      // que basta con declarar tambien el estado cerrado para que el dialogo
      // salga en lugar de desaparecer de golpe.
      'fixed inset-0 z-50 bg-scrim backdrop-blur-md',
      'data-[state=open]:animate-overlay-show data-[state=closed]:animate-overlay-hide',
      className
    )}
    {...props}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

interface DialogContentProps extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  size?: 'default' | 'lg'
}

export const DialogContent = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Content>, DialogContentProps>(
  ({ className, children, size = 'default', ...props }, ref) => (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'fixed left-1/2 top-1/2 z-50 grid w-[calc(100%-40px)] -translate-x-1/2 -translate-y-1/2 gap-5',
          'max-h-[calc(100vh-40px)] overflow-y-auto rounded-xl border border-border bg-card p-6 text-card-foreground outline-none',
          // Luz de canto + halo de marca: el dialogo flota sobre la escena en
          // lugar de recortarse sobre ella.
          'shadow-[inset_0_1px_0_var(--edge-light),0_24px_70px_-12px_rgba(0,0,0,.7),0_0_0_1px_var(--glow-brand)]',
          'data-[state=open]:animate-content-show data-[state=closed]:animate-content-hide',
          size === 'lg' ? 'max-w-[660px]' : 'max-w-[520px]',
          className
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className={cn(
            'absolute right-4 top-4 rounded-md p-1.5 text-muted-foreground outline-none',
            'transition-[background-color,color,transform] duration-[var(--dur-hover)] ease-out',
            'hover:bg-muted hover:text-foreground active:scale-95 focus-visible:ring-2 focus-visible:ring-ring'
          )}>
          <X size={16} />
          <span className="sr-only">Cerrar</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPortal>
  )
)
DialogContent.displayName = DialogPrimitive.Content.displayName

export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>): React.JSX.Element {
  return <div className={cn('flex flex-col gap-1 pr-6', className)} {...props} />
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>): React.JSX.Element {
  return <div className={cn('flex items-center justify-end gap-2 pt-1', className)} {...props} />
}

export const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title ref={ref} className={cn('text-lg font-semibold leading-none', className)} {...props} />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

export const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description ref={ref} className={cn('text-xs leading-relaxed text-muted-foreground', className)} {...props} />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName
