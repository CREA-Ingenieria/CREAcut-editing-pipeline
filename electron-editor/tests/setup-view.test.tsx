import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { LaunchView, SetupView } from '../src/renderer/src/views/SetupView'
import { applySetupProgress, initialSetupSteps, type BackendSetupStatus } from '../src/shared/backend-setup'

const noop = (): void => {}
const render = (status: BackendSetupStatus, showDetail = false): string =>
  renderToStaticMarkup(<SetupView status={status} showDetail={showDetail} onRetry={noop} onToggleDetail={noop} />)

function runningAt(stepIndex: number, extra: { message?: string; percent?: number } = {}): BackendSetupStatus {
  let status: BackendSetupStatus = { state: 'running', steps: initialSetupSteps() }
  status.steps.slice(0, stepIndex).forEach((step) => {
    status = applySetupProgress(status, { stepId: step.id, state: 'done' })
  })
  return applySetupProgress(status, { stepId: status.steps[stepIndex].id, state: 'running', ...extra })
}

describe('SetupView', () => {
  it('presenta la preparación con la marca de CREAcut y una región viva', () => {
    const markup = render(runningAt(1, { message: 'Resolved 24 packages' }))
    expect(markup).toContain('Preparando CREAcut para tu Mac')
    expect(markup).toContain('creator-hero__brand')
    expect(markup).toContain('DE TU IDEA AL ÚLTIMO CORTE')
    expect(markup).toContain('aria-live="polite"')
    expect(markup).toContain('fx-aurora')
    expect(markup).toContain('Resolved 24 packages')
  })

  it('la región viva anuncia solo el estado de los pasos, no cada línea', () => {
    const markup = render(runningAt(1, { message: 'Resolved 24 packages' }))
    expect(markup.match(/aria-live=/g)).toHaveLength(1)
    const live = /<p[^>]*aria-live="polite"[^>]*>([^<]*)<\/p>/.exec(markup)
    expect(live?.[1]).toBe(
      'Python 3.12: listo. PyTorch: en curso. Dependencias: pendiente. Comprobación: pendiente. Whisper: pendiente.'
    )
    expect(markup).not.toMatch(/<ol[^>]*aria-live/)
  })

  it('marca el estado de cada paso', () => {
    const markup = render(runningAt(2))
    expect(markup.match(/data-state="done"/g)).toHaveLength(2)
    expect(markup.match(/data-state="running"/g)).toHaveLength(1)
    expect(markup.match(/data-state="pending"/g)).toHaveLength(2)
    expect(markup).toContain('live-dot')
  })

  it('usa la barra indeterminada mientras no hay porcentaje y no ofrece Reintentar', () => {
    const markup = render(runningAt(0))
    expect(markup).toContain('busy-bar')
    expect(markup).not.toContain('role="progressbar"')
    expect(markup).not.toContain('Reintentar')
    expect(markup).toContain('Mantén la conexión a Internet')
  })

  it('muestra el porcentaje de Whisper como barra determinada', () => {
    const markup = render(runningAt(4, { message: 'large-v3.pt: 42%', percent: 42 }))
    expect(markup).toContain('role="progressbar"')
    expect(markup).toContain('aria-label="Whisper"')
    expect(markup).toContain('aria-valuenow="42"')
    expect(markup).toContain('width:42%')
    expect(markup).not.toContain('busy-bar')
  })

  it('ante un fallo ofrece Reintentar, el consejo y el detalle', () => {
    const failed: BackendSetupStatus = {
      ...applySetupProgress(runningAt(1), { stepId: 'torch', state: 'failed', message: 'No se pudo instalar PyTorch.' }),
      error: 'No se pudo instalar PyTorch.',
      detail: 'error: Failed to fetch\nConnection reset',
      logPath: '/Users/ana/Library/Logs/CREAcut/backend-setup.log'
    }
    const closed = render(failed)
    expect(closed).toContain('Reintentar')
    expect(closed).toContain('role="alert"')
    expect(closed).toContain('No se pudo instalar PyTorch. Revisa la conexión y el espacio libre, y vuelve a intentarlo.')
    expect(closed).toContain('Ver detalle')
    expect(closed).not.toContain('Connection reset')
    expect(closed).toContain('backend-setup.log')
    expect(closed).not.toContain('busy-bar')

    expect(render(failed, true)).toContain('Connection reset')
  })

  it('si no se pudo lanzar uv o Python, el consejo apunta a Privacidad y seguridad', () => {
    const failed: BackendSetupStatus = {
      ...applySetupProgress(runningAt(0), { stepId: 'python', state: 'failed' }),
      error: 'No se pudo ejecutar uv, el instalador de Python que viene con CREAcut.',
      errorKind: 'launch'
    }
    const markup = render(failed)
    expect(markup).toContain(
      'No se pudo ejecutar uv, el instalador de Python que viene con CREAcut. ' +
      'Abre Ajustes del Sistema → Privacidad y seguridad y permite CREAcut; luego vuelve a intentarlo.'
    )
    expect(markup).not.toContain('Revisa la conexión')
  })
})

describe('LaunchView', () => {
  it('mientras se comprueba el entorno muestra la marca y una barra indeterminada', () => {
    const markup = renderToStaticMarkup(<LaunchView />)
    expect(markup).toContain('Abriendo CREAcut…')
    expect(markup).toContain('creator-hero__brand')
    expect(markup).toContain('hero-surface')
    expect(markup).toContain('fx-aurora')
    expect(markup).toContain('busy-bar')
    expect(markup).toContain('role="status"')
    expect(markup).not.toContain('Reintentar')
  })
})
