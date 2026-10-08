export function formatTime(value: number, milliseconds = false): string {
  const safeValue = Number.isFinite(value) ? Math.max(0, value) : 0
  const totalMilliseconds = Math.round(safeValue * 1000)
  const hours = Math.floor(totalMilliseconds / 3_600_000)
  const minutes = Math.floor((totalMilliseconds % 3_600_000) / 60_000)
  const seconds = Math.floor((totalMilliseconds % 60_000) / 1000)
  const millis = totalMilliseconds % 1000
  const clock = hours
    ? `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
    : `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  return milliseconds ? `${clock}.${millis.toString().padStart(3, '0')}` : clock
}

export function compactPath(value: string): string {
  const parts = value.replaceAll('\\', '/').split('/').filter(Boolean)
  if (parts.length <= 3) return value
  return `…/${parts.slice(-3).join('/')}`
}

/**
 * Fecha relativa corta en español para la galería de proyectos.
 *
 * Compara días de calendario, no diferencias de 24 horas: un proyecto abierto
 * anoche debe leerse "Ayer" aunque hayan pasado nueve horas. Fuera de la
 * primera semana se cae a la fecha local, que ya es suficientemente concreta.
 */
export function formatRelativeDate(value: string, now: Date = new Date()): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const startOfDay = (moment: Date): number =>
    new Date(moment.getFullYear(), moment.getMonth(), moment.getDate()).getTime()
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  if (days <= 0) return 'Hoy'
  if (days === 1) return 'Ayer'
  if (days < 7) return `Hace ${days} días`
  return date.toLocaleDateString()
}
