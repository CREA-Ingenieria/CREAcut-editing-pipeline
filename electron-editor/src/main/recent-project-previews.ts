import { createHash } from 'node:crypto'
import { readFile, readdir, stat } from 'node:fs/promises'
import { dirname, extname, join, resolve } from 'node:path'
import type { RecentProject } from '../shared/contracts'

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {}
}

function spread<T>(items: T[]): T[] {
  if (items.length <= 3) return items
  return [items[0], items[Math.floor(items.length / 2)], items[items.length - 1]]
}

/** Read existing artwork only. Listing recent projects never opens a project
 * in Python or starts thumbnail generation, transcription or video decoding. */
export async function withProjectPreviews(
  project: RecentProject, register: (path: string) => string
): Promise<RecentProject> {
  const previewImages: NonNullable<RecentProject['previewImages']> = []
  try {
    if ((await stat(project.path)).size > 32 * 1024 * 1024) return { ...project, previewImages }
    const saved = record(JSON.parse((await readFile(project.path, 'utf8')).replace(/^\uFEFF/, '')))
    const projectDir = dirname(project.path)
    const slides = record(record(saved.extensions)['creacut.slides'])
    const pages = Array.isArray(slides.pages) ? slides.pages : []
    const candidates: Array<{ path: string; label: string }> = []
    for (const [index, value] of pages.entries()) {
      const page = record(value)
      for (const image of [page.thumbnail_path, page.image_path]) {
        if (typeof image !== 'string' || !/\.(png|jpe?g|webp)$/i.test(extname(image))) continue
        const path = resolve(projectDir, image)
        try {
          if ((await stat(path)).isFile()) {
            candidates.push({ path, label: `Diapositiva ${index + 1}` })
            break
          }
        } catch { /* A missing asset must not prevent opening its project. */ }
      }
    }
    if (!candidates.length) {
      const source = record(saved.source)
      if (typeof source.path === 'string' && typeof source.duration_s === 'number' && Number.isFinite(source.duration_s)) {
        const sourcePath = resolve(projectDir, source.path)
        const info = await stat(sourcePath, { bigint: true })
        // Same cache identity as bridge.py; BigInt preserves nanoseconds.
        const identity = `${sourcePath}|${info.size}|${info.mtimeNs}|${source.duration_s.toFixed(6)}`
        const digest = createHash('sha256').update(identity, 'utf8').digest('hex').slice(0, 18)
        const cache = join(projectDir, '.creacut-cache', `web-${digest}`)
        const names = (await readdir(cache)).filter((name) => /^thumb-[\d.]+\.jpg$/i.test(name))
          .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
        for (const name of spread(names)) candidates.push({ path: join(cache, name), label: 'Fotograma del video' })
      }
    }
    for (const item of spread(candidates)) previewImages.push({ url: register(item.path), label: item.label })
  } catch { /* Artwork is optional; the project remains available. */ }
  return { ...project, previewImages }
}
