import { useEffect, useState } from 'react'
import { AlertCircle, X } from 'lucide-react'
import { cn } from '../lib/utils'

/**
 * Aviso de error del editor.
 *
 * Antes era una banda insertada entre la barra superior y la rejilla de
 * paneles: al aparecer empujaba hacia abajo el visor y la línea de tiempo, así
 * que un fallo al guardar movía el fotograma que el usuario estaba mirando y
 * desplazaba el cabezal bajo el cursor. Ahora flota sobre la columna central y
 * no participa del reparto de espacio.
 *
 * Aparece sobre el visor y no sobre la línea de tiempo: el visor es pasivo
 * mientras se lee un error, la línea de tiempo no — tapar el cabezal o el
 * bloque que se estaba arrastrando sería peor que tapar el fotograma.
 *
 * No se descarta solo: un error es información que el usuario tiene que poder
 * leer entera, y varios de estos mensajes traen rutas largas. Lo que sí se
 * anima es la entrada y la salida (~200 ms), para que un mensaje nuevo se
 * distinga de otro que ya estaba.
 */
interface ErrorToastProps {
  message: string | null
  onDismiss: () => void
}

const EXIT_MS = 160

export function ErrorToast({ message, onDismiss }: ErrorToastProps): React.JSX.Element | null {
  // El mensaje se retiene durante la salida: sin esto el texto desaparece en
  // el primer fotograma y solo se desvanece una caja vacía.
  const [visible, setVisible] = useState<string | null>(message)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (message) {
      setVisible(message)
      setLeaving(false)
      return
    }
    if (!visible) return
    setLeaving(true)
    const timer = window.setTimeout(() => {
      setVisible(null)
      setLeaving(false)
    }, EXIT_MS)
    return () => window.clearTimeout(timer)
  }, [message, visible])

  if (!visible) return null

  return (
    <div className="pointer-events-none absolute inset-x-0 top-12 z-30 flex justify-center px-4">
      <div
        role="alert"
        data-leaving={leaving ? 'true' : 'false'}
        className={cn(
          'toast pointer-events-auto flex max-w-[min(720px,92vw)] items-start gap-2.5 rounded-lg border border-destructive/40',
          'bg-popover px-3.5 py-2.5 text-[11px] leading-relaxed text-foreground shadow-xl'
        )}
      >
        <AlertCircle size={15} className="mt-px shrink-0 text-destructive" />
        <span className="min-w-0 flex-1 whitespace-pre-line break-words">{visible}</span>
        <button
          type="button"
          aria-label="Descartar aviso"
          className="-mr-1 shrink-0 rounded-sm p-1 text-muted-foreground outline-none transition-colors duration-[var(--dur-hover)] ease-out hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          onClick={onDismiss}
        >
          <X size={13} />
        </button>
      </div>
    </div>
  )
}
