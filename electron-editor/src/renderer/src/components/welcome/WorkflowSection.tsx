import { FileVideo2, Scissors, Upload } from 'lucide-react'

/**
 * Cierre de la pantalla de bienvenida.
 *
 * Cumple dos funciones. La primera es informativa: resume el recorrido del
 * pipeline y los atajos del editor. La segunda es estructural: las tarjetas de
 * la galería se sueltan juntas al final del apilado y salen de la pantalla, así
 * que debajo tiene que haber contenido real; sin él, el recorrido termina de
 * golpe en cuanto acaba el apilado.
 *
 * Es contenido estático: no recibe datos ni callbacks.
 */
const STEPS = [
  {
    icon: FileVideo2,
    title: 'Analizar',
    body: 'Whisper transcribe el video en tu equipo y CREAcut alinea el resultado con el guion.'
  },
  {
    icon: Scissors,
    title: 'Revisar',
    body: 'Compara tomas, ajusta los cortes en el timeline y descarta lo que sobre sin tocar el original.'
  },
  {
    icon: Upload,
    title: 'Exportar',
    body: 'El render final se genera localmente a partir de la edición que dejaste aprobada.'
  }
] as const

const SHORTCUTS = [
  ['Ctrl + O', 'Abrir proyecto'],
  ['Ctrl + S', 'Guardar'],
  ['Ctrl + Shift + S', 'Guardar como'],
  ['Ctrl + E', 'Exportar'],
  ['Ctrl + Z', 'Deshacer'],
  ['Espacio', 'Reproducir / pausar']
] as const

export function WorkflowSection(): React.JSX.Element {
  return (
    <section className="mx-auto w-[min(1080px,calc(100%-64px))] pb-24 pt-20">
      <span className="block text-[9px] font-extrabold uppercase tracking-[.13em] text-primary">
        Cómo funciona
      </span>
      <h2 className="mt-1.5 text-[clamp(24px,3vw,34px)] font-semibold tracking-[-.04em]">
        Tres pasos, todo en tu equipo
      </h2>

      <div className="mt-7 grid gap-3.5 sm:grid-cols-3">
        {STEPS.map(({ icon: Icon, title, body }) => (
          <article
            key={title}
            className="rounded-xl border border-border-soft bg-card/60 p-4 backdrop-blur-[6px]"
          >
            <Icon size={20} className="text-primary" />
            <h3 className="mt-2.5 text-sm font-semibold">{title}</h3>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{body}</p>
          </article>
        ))}
      </div>

      <div className="mt-8 rounded-xl border border-border-soft bg-card/40 p-4">
        <span className="block text-[9px] uppercase tracking-[.1em] text-muted-foreground">
          Atajos del editor
        </span>
        <ul className="mt-2.5 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
          {SHORTCUTS.map(([keys, action]) => (
            <li key={keys} className="flex items-center justify-between gap-3 text-[11px]">
              <span className="text-muted-foreground">{action}</span>
              <kbd className="rounded-sm border border-border bg-muted px-1.5 py-0.5 font-sans text-[10px] text-foreground">
                {keys}
              </kbd>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
