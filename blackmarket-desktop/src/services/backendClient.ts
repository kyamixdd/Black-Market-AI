export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export type BackendClientOptions = {
  baseUrl: string
  authorization?: () => Record<string, string> | undefined
  fetcher?: FetchLike
}

export function createBackendClient(options: BackendClientOptions) {
  const fetcher = options.fetcher ?? fetch
  const headers = () => options.authorization?.() ?? {}

  async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetcher(`${options.baseUrl}${path}`, {
      ...init,
      headers: {
        ...headers(),
        ...(init.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(init.headers as Record<string, string> | undefined),
      },
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = typeof payload.detail === 'string' ? payload.detail : `${response.status} ${response.statusText}`
      throw new Error(detail)
    }
    return payload as T
  }

  return {
    get: <T>(path: string) => requestJson<T>(path),
    post: <T>(path: string, body: unknown) => requestJson<T>(path, { method: 'POST', body: JSON.stringify(body) }),
    requestJson,
  }
}

export const backendBaseUrl = () =>
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
    ? 'http://127.0.0.1:8765/api'
    : '/api/backend'
