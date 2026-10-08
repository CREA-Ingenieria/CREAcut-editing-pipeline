import * as React from 'react'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '../../lib/utils'
import { useTabIndicator } from '../../hooks/useTabIndicator'

export const Tabs = TabsPrimitive.Root

/**
 * Lista de pestañas con una barra que viaja entre ellas.
 *
 * El indicador es un hermano de los disparadores, no un borde de cada uno: así
 * el cambio de pestaña se lee como un desplazamiento y no como dos parpadeos
 * independientes. `useTabIndicator` se encarga de medir; aquí solo se reserva
 * el sitio (`relative`) y se marca como decorativo para los lectores de
 * pantalla, que ya anuncian la pestaña activa por `aria-selected`.
 */
export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, children, ...props }, ref) => {
  const { listRef, indicatorRef } = useTabIndicator<HTMLDivElement>()
  return (
    <TabsPrimitive.List
      ref={mergeRefs(ref, listRef)}
      className={cn('relative inline-flex items-center gap-1 border-b border-border', className)}
      {...props}
    >
      {children}
      <span ref={indicatorRef} data-ready="false" aria-hidden className="tab-indicator" />
    </TabsPrimitive.List>
  )
})
TabsList.displayName = TabsPrimitive.List.displayName

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      // El borde inferior desaparece: ese trabajo lo hace ahora el indicador.
      // Solo queda la transición de color, que a esta frecuencia de uso debe
      // ser casi imperceptible (160ms) y nunca desplazar el texto.
      'relative px-2 py-2.5 text-xs font-semibold text-muted-foreground outline-none',
      'transition-colors duration-[var(--dur-hover)] ease-out',
      'hover:text-foreground data-[state=active]:text-foreground',
      'focus-visible:ring-2 focus-visible:ring-ring focus-visible:rounded-sm',
      className
    )}
    {...props}
  />
))
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName

export const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      // Fundido de entrada muy corto. El contenido no se desplaza: son paneles
      // largos de texto y moverlos al cambiar de pestaña marea.
      'outline-none data-[state=active]:animate-[fade-in_var(--dur-hover)_var(--ease-out)]',
      className
    )}
    {...props}
  />
))
TabsContent.displayName = TabsPrimitive.Content.displayName

/**
 * Variante en pastilla para conmutadores de vista (original / propuesta /
 * previsualización). Aquí el indicador es el propio fondo activo, que se
 * desliza de una opción a otra en lugar de aparecer y desaparecer.
 */
export const SegmentedList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, children, ...props }, ref) => {
  const { listRef, indicatorRef } = useTabIndicator<HTMLDivElement>()
  return (
    <TabsPrimitive.List
      ref={mergeRefs(ref, listRef)}
      className={cn(
        'relative inline-grid grid-flow-col rounded-md border border-border bg-background p-0.5',
        className
      )}
      {...props}
    >
      <span ref={indicatorRef} data-ready="false" aria-hidden className="tab-indicator tab-indicator--pill" />
      {children}
    </TabsPrimitive.List>
  )
})
SegmentedList.displayName = 'SegmentedList'

export const SegmentedTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      // `relative` para quedar por encima de la pastilla, que va detrás.
      'relative rounded-[5px] px-3 py-1.5 text-[11px] font-semibold text-muted-foreground outline-none',
      'transition-colors duration-[var(--dur-hover)] ease-out',
      'hover:text-foreground data-[state=active]:text-foreground',
      'focus-visible:ring-2 focus-visible:ring-ring',
      className
    )}
    {...props}
  />
))
SegmentedTrigger.displayName = 'SegmentedTrigger'

/**
 * Une la referencia que expone el componente con la que necesita el hook de
 * medida. Sin esto habría que elegir una de las dos.
 */
function mergeRefs<T>(...refs: Array<React.Ref<T> | undefined>): React.RefCallback<T> {
  return (value) => {
    for (const ref of refs) {
      if (typeof ref === 'function') ref(value)
      else if (ref) (ref as React.MutableRefObject<T | null>).current = value
    }
  }
}
