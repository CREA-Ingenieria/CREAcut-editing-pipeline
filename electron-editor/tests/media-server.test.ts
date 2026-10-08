import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { LocalMediaServer } from '../src/main/media-server'

describe('LocalMediaServer', () => {
  let directory: string
  let filePath: string
  let server: LocalMediaServer
  let mediaUrl: string

  beforeEach(async () => {
    directory = await mkdtemp(join(tmpdir(), 'creacut-media-test-'))
    filePath = join(directory, 'video.mp4')
    await writeFile(filePath, Buffer.from('0123456789abcdef'))
    server = new LocalMediaServer()
    await server.start()
    mediaUrl = server.register(filePath)
  })

  afterEach(async () => {
    await server.close()
    await rm(directory, { recursive: true, force: true })
  })

  it('sirve el archivo completo con cabeceras multimedia', async () => {
    const response = await fetch(mediaUrl)

    expect(response.status).toBe(200)
    expect(response.headers.get('accept-ranges')).toBe('bytes')
    expect(response.headers.get('content-type')).toBe('video/mp4')
    expect(response.headers.get('content-length')).toBe('16')
    expect(await response.text()).toBe('0123456789abcdef')
  })

  it('responde rangos para que Chromium pueda buscar y reproducir audio', async () => {
    const response = await fetch(mediaUrl, { headers: { Range: 'bytes=4-8' } })

    expect(response.status).toBe(206)
    expect(response.headers.get('content-range')).toBe('bytes 4-8/16')
    expect(response.headers.get('content-length')).toBe('5')
    expect(await response.text()).toBe('45678')
  })

  it('acepta rangos de sufijo y solicitudes HEAD', async () => {
    const suffix = await fetch(mediaUrl, { headers: { Range: 'bytes=-4' } })
    const head = await fetch(mediaUrl, { method: 'HEAD' })

    expect(suffix.status).toBe(206)
    expect(await suffix.text()).toBe('cdef')
    expect(head.status).toBe(200)
    expect(head.headers.get('content-length')).toBe('16')
    expect(await head.text()).toBe('')
  })

  it('rechaza rangos inválidos y recursos no registrados', async () => {
    const invalid = await fetch(mediaUrl, { headers: { Range: 'bytes=50-60' } })
    server.clear()
    const cleared = await fetch(mediaUrl)

    expect(invalid.status).toBe(416)
    expect(invalid.headers.get('content-range')).toBe('bytes */16')
    expect(cleared.status).toBe(404)
  })
})
