export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export type BackendClientOptions = {
  baseUrl: string
  authorization?: () => Record<string, string> | undefined
  fetcher?: FetchLike
  timeoutMs?: number
  retries?: number
}

export type BackendRequestMetrics = {
  windowSeconds: number
  requestCount: number
  failureCount: number
  averageDurationMs: number
  p95DurationMs: number
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

function safeEndpoint(path: string): string {
  try {
    const parsed = new URL(path, 'http://blackmarket.local')
    return parsed.pathname.slice(0, 200) || '/'
  } catch {
    return path.split(/[?#]/, 1)[0].slice(0, 200)
  }
}

const RETRYABLE_STATUS = new Set([502, 503, 504])
const RETRY_DELAY_MS = 250

export function createBackendClient(options: BackendClientOptions) {
  const fetcher = options.fetcher ?? fetch
  const timeoutMs = Math.max(1000, options.timeoutMs ?? 10000)
  const retries = Math.max(0, Math.min(2, options.retries ?? 2))
  const headers = () => options.authorization?.() ?? {}
  const requestSamples: { completedAt: number; durationMs: number; succeeded: boolean }[] = []

  function getMetrics(): BackendRequestMetrics {
    const now = Date.now()
    const windowStart = now - 60_000
    while (requestSamples.length && requestSamples[0].completedAt < windowStart) requestSamples.shift()
    const durations = requestSamples.map((sample) => sample.durationMs).sort((left, right) => left - right)
    const p95Index = durations.length ? Math.ceil(durations.length * 0.95) - 1 : 0
    return {
      windowSeconds: 60,
      requestCount: requestSamples.length,
      failureCount: requestSamples.filter((sample) => !sample.succeeded).length,
      averageDurationMs: durations.length ? Math.round(durations.reduce((total, duration) => total + duration, 0) / durations.length) : 0,
      p95DurationMs: durations[p95Index] ?? 0,
    }
  }

  async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const startedAt = Date.now()
    let succeeded = false
    let statusCode: number | undefined
    try {
      const result = await performRequest<T>(path, init, (status) => { statusCode = status })
      succeeded = true
      return result
    } catch (error) {
      const code = error instanceof BackendRequestError ? error.code : 'network'
      const status = error instanceof BackendRequestError ? error.status : statusCode
      recordFrontendDiagnostic({
        level: 'ERROR',
        event: 'frontend_api_request_failed',
        operation: `${(init.method ?? 'GET').toUpperCase()} ${safeEndpoint(path)}`,
        status: 'FAILURE',
        duration_ms: Date.now() - startedAt,
        endpoint: safeEndpoint(path),
        status_code: status,
        detail: error instanceof Error ? error.message : 'Unexpected API request failure.',
        recommendation: code === 'timeout'
          ? 'Check backend responsiveness and reduce concurrent refresh load.'
          : status === 401
            ? 'Re-establish the desktop API session and verify its per-launch token.'
            : status === 403
              ? 'Check local API access policy and request origin.'
              : status && status >= 500
                ? 'Inspect backend process logs around this timestamp and endpoint for the server-side exception.'
                : 'Check backend availability, endpoint status, and network connectivity.',
      })
      throw error
    } finally {
      const durationMs = Date.now() - startedAt
      requestSamples.push({ completedAt: Date.now(), durationMs, succeeded })
      if (requestSamples.length > 600) requestSamples.splice(0, requestSamples.length - 600)
      if (succeeded) {
        recordFrontendDiagnostic({
          level: 'INFO',
          event: 'frontend_api_request_completed',
          operation: `${(init.method ?? 'GET').toUpperCase()} ${safeEndpoint(path)}`,
          status: 'SUCCESS',
          duration_ms: durationMs,
          endpoint: safeEndpoint(path),
          status_code: statusCode,
        })
      }
    }
  }

  async function performRequest<T>(path: string, init: RequestInit, onStatus: (status: number) => void): Promise<T> {
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
        onStatus(response.status)
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
    getMetrics,
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
import { recordFrontendDiagnostic } from './frontendDiagnostics.ts'

function localCommunityOwner() {
  try {
    let value = localStorage.getItem('bm_community_owner')
    if (!value || !/^[a-f0-9-]{36}$/i.test(value)) {
      value = crypto.randomUUID()
      localStorage.setItem('bm_community_owner', value)
    }
    return value
  } catch {
    return undefined
  }
}

const client = createBackendClient({
  baseUrl: backendBaseUrl(),
  authorization: () => {
    if (!isDesktopRuntime()) return undefined
    const owner = localCommunityOwner()
    return { ...getApiAuthorization(), ...(owner ? { 'X-BM-Community-Owner': owner } : {}) }
  },
})

export const validateBackendConnection = () => client.healthCheck()
export const getBackendRequestMetrics = () => client.getMetrics()

export const requestJson = <T>(path: string, api = true): Promise<T | null> =>
  api ? client.get<T>(path).catch((error: unknown) => {
    console.error(`Unable to load ${path}`, error)
    return null
  }) : client.requestJson<T>(`http://127.0.0.1:8765${path}`).catch(() => null)

export const mutateJson = <T>(path: string, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> =>
  client.requestJson<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
