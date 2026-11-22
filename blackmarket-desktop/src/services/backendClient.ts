export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export type BackendClientOptions = {
  baseUrl: string
  authorization?: () => Record<string, string> | undefined
  fetcher?: FetchLike
  timeoutMs?: number
  retries?: number
}

export class BackendRequestError extends Error {
  readonly status?: number
  readonly code: 'timeout' | 'network' | 'http'

  constructor(message: string, code: BackendRequestError['code'], status?: number) {
    super(message)
    this.name = 'BackendRequestError'
    this.code = code
    this.status = status
  }
}

const RETRYABLE_STATUS = new Set([502, 503, 504])
const RETRY_DELAY_MS = 250

export function createBackendClient(options: BackendClientOptions) {
  const fetcher = options.fetcher ?? fetch
  const timeoutMs = Math.max(1000, options.timeoutMs ?? 10000)
  const retries = Math.max(0, Math.min(2, options.retries ?? 2))
  const headers = () => options.authorization?.() ?? {}

  async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const url = path.startsWith('http://') || path.startsWith('https://') ? path : `${options.baseUrl}${path}`
    const method = (init.method ?? 'GET').toUpperCase()
    const safeToRetry = method === 'GET' || method === 'HEAD'
    const attempts = safeToRetry ? retries + 1 : 1
    let lastError: unknown

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const controller = new AbortController()
      const externalSignal = init.signal
      const abortFromCaller = () => controller.abort(externalSignal?.reason)
      if (externalSignal?.aborted) abortFromCaller()
      else externalSignal?.addEventListener('abort', abortFromCaller, { once: true })
      const timeout = setTimeout(() => controller.abort(new DOMException('Backend request timed out', 'TimeoutError')), timeoutMs)

      try {
        const response = await fetcher(url, {
          ...init,
          signal: controller.signal,
          headers: {
            ...headers(),
            ...(init.body === undefined ? {} : { 'Content-Type': 'application/json' }),
            ...(init.headers as Record<string, string> | undefined),
          },
          cache: 'no-store',
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          const detail = typeof payload.detail === 'string'
            ? payload.detail
            : typeof payload.error === 'string'
              ? payload.error
              : `${response.status} ${response.statusText}`
          if (safeToRetry && RETRYABLE_STATUS.has(response.status) && attempt < attempts - 1) {
            lastError = new BackendRequestError(detail, 'http', response.status)
          } else {
            throw new BackendRequestError(detail, 'http', response.status)
          }
        } else {
          return payload as T
        }
      } catch (error) {
        if (error instanceof BackendRequestError && error.code === 'http' && error.status && !RETRYABLE_STATUS.has(error.status)) throw error
        if (externalSignal?.aborted) throw error
        lastError = error
        if (controller.signal.aborted) {
          throw new BackendRequestError(`Backend request timed out after ${timeoutMs} ms: ${url}`, 'timeout')
        }
        if (attempt >= attempts - 1) {
          if (error instanceof BackendRequestError) throw error
          throw new BackendRequestError(`Backend is unreachable: ${url}`, 'network')
        }
      } finally {
        clearTimeout(timeout)
        externalSignal?.removeEventListener('abort', abortFromCaller)
      }

      if (attempt < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS * (attempt + 1)))
      }
    }
    throw lastError instanceof Error ? lastError : new BackendRequestError('Backend request failed', 'network')
  }

  return {
    get: <T>(path: string) => requestJson<T>(path),
    post: <T>(path: string, body: unknown) => requestJson<T>(path, { method: 'POST', body: JSON.stringify(body) }),
    requestJson,
    healthCheck: () => requestJson<Record<string, unknown>>('/health'),
  }
}

/** One transport selection point shared by REST and event transports. */
export const isDesktopRuntime = () =>
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

export const backendBaseUrl = () => isDesktopRuntime()
  ? 'http://127.0.0.1:8765/api'
  : '/api/backend'

export const backendEventStreamUrl = () => isDesktopRuntime()
  ? 'http://127.0.0.1:8765/api/events/stream'
  : '/api/backend/events/stream'

export const backendWebSocketUrl = () => {
  if (isDesktopRuntime()) return 'ws://127.0.0.1:8765/ws'
  // Hosted browsers use the authenticated same-origin SSE proxy, not a desktop socket.
  return backendEventStreamUrl()
}

import { getApiAuthorization } from './localAuth.js'

const client = createBackendClient({
  baseUrl: backendBaseUrl(),
  authorization: () => isDesktopRuntime() ? getApiAuthorization() : undefined,
})

export const validateBackendConnection = () => client.healthCheck()

export const requestJson = <T>(path: string, api = true): Promise<T | null> =>
  api ? client.get<T>(path).catch((error: unknown) => {
    console.error(`Unable to load ${path}`, error)
    return null
  }) : client.requestJson<T>(`http://127.0.0.1:8765${path}`).catch(() => null)

export const mutateJson = <T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> =>
  client.requestJson<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
