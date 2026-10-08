import { randomUUID } from 'node:crypto'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import type { AddressInfo } from 'node:net'
import { extname, resolve } from 'node:path'

interface ByteRange {
  start: number
  end: number
}

function contentType(filePath: string): string {
  const types: Record<string, string> = {
    '.avi': 'video/x-msvideo',
    '.bmp': 'image/bmp',
    '.jpeg': 'image/jpeg',
    '.jpg': 'image/jpeg',
    '.m4v': 'video/x-m4v',
    '.mkv': 'video/x-matroska',
    '.mov': 'video/quicktime',
    '.mp4': 'video/mp4',
    '.png': 'image/png',
    '.webm': 'video/webm',
    '.webp': 'image/webp'
  }
  return types[extname(filePath).toLowerCase()] ?? 'application/octet-stream'
}

function parseRange(header: string, size: number): ByteRange | null {
  const match = /^bytes=(\d*)-(\d*)$/i.exec(header.trim())
  if (!match || size <= 0 || (!match[1] && !match[2])) return null

  let start: number
  let end: number
  if (!match[1]) {
    const suffixLength = Number(match[2])
    if (!Number.isSafeInteger(suffixLength) || suffixLength <= 0) return null
    start = Math.max(0, size - suffixLength)
    end = size - 1
  } else {
    start = Number(match[1])
    end = match[2] ? Number(match[2]) : size - 1
  }

  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end)) return null
  if (start < 0 || start >= size || end < start) return null
  return { start, end: Math.min(end, size - 1) }
}

/**
 * Loopback-only HTTP server for local media. Chromium's media pipeline uses
 * standard HTTP byte ranges here, so seeking and audio/video buffering follow
 * the same path as a normal web video without exposing arbitrary file paths.
 */
export class LocalMediaServer {
  private server: Server | null = null
  private port: number | null = null
  private readonly paths = new Map<string, string>()

  async start(): Promise<void> {
    if (this.server && this.port !== null) return
    await new Promise<void>((resolveStart, rejectStart) => {
      const server = createServer((request, response) => this.handle(request, response))
      server.once('error', rejectStart)
      server.listen(0, '127.0.0.1', () => {
        const address = server.address() as AddressInfo
        this.server = server
        this.port = address.port
        server.removeListener('error', rejectStart)
        resolveStart()
      })
    })
  }

  register(filePath: string): string {
    if (this.port === null) throw new Error('El servidor multimedia todavía no está disponible')
    const token = randomUUID()
    this.paths.set(token, resolve(filePath))
    return `http://127.0.0.1:${this.port}/media/${token}`
  }

  clear(): void {
    this.paths.clear()
  }

  async close(): Promise<void> {
    this.paths.clear()
    const server = this.server
    this.server = null
    this.port = null
    if (!server) return
    await new Promise<void>((resolveClose) => server.close(() => resolveClose()))
  }

  private handle(request: IncomingMessage, response: ServerResponse): void {
    response.setHeader('Access-Control-Allow-Origin', '*')
    response.setHeader('Cross-Origin-Resource-Policy', 'cross-origin')
    response.setHeader('Cache-Control', 'no-store')

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      response.writeHead(405, { Allow: 'GET, HEAD' })
      response.end()
      return
    }

    const requestUrl = new URL(request.url ?? '/', 'http://127.0.0.1')
    const match = /^\/media\/([0-9a-f-]+)$/i.exec(requestUrl.pathname)
    const target = match ? this.paths.get(match[1]) : undefined
    if (!target || !existsSync(target)) {
      response.writeHead(404)
      response.end('Recurso no disponible')
      return
    }

    const size = statSync(target).size
    const rangeHeader = Array.isArray(request.headers.range)
      ? request.headers.range[0]
      : request.headers.range
    const headers: Record<string, string> = {
      'Accept-Ranges': 'bytes',
      'Content-Type': contentType(target)
    }

    let start = 0
    let end = Math.max(0, size - 1)
    let status = 200
    if (rangeHeader) {
      const range = parseRange(rangeHeader, size)
      if (!range) {
        response.writeHead(416, { ...headers, 'Content-Range': `bytes */${size}` })
        response.end()
        return
      }
      start = range.start
      end = range.end
      status = 206
      headers['Content-Range'] = `bytes ${start}-${end}/${size}`
    }
    headers['Content-Length'] = String(end - start + 1)
    response.writeHead(status, headers)

    if (request.method === 'HEAD') {
      response.end()
      return
    }

    const stream = createReadStream(target, { start, end })
    stream.on('error', (error) => response.destroy(error))
    response.on('close', () => stream.destroy())
    stream.pipe(response)
  }
}
