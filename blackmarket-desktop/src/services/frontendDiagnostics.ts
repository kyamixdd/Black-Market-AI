export type FrontendDiagnosticLevel = 'INFO' | 'WARNING' | 'ERROR'
export type FrontendDiagnosticStatus = 'SUCCESS' | 'FAILURE' | 'WARNING'

export type FrontendDiagnosticEvent = {
  id: string
  timestamp: string
  level: FrontendDiagnosticLevel
  event: string
  operation: string
  status: FrontendDiagnosticStatus
  duration_ms?: number
  endpoint?: string
  status_code?: number
  detail?: string
  recommendation?: string
}

const MAX_EVENTS = 500
const MAX_PENDING_EVENTS = 1000
const events: FrontendDiagnosticEvent[] = []
const pending: FrontendDiagnosticEvent[] = []
const listeners = new Set<(event: FrontendDiagnosticEvent) => void>()
let sequence = 0

function safeEndpoint(value: string): string {
  try {
    const url = new URL(value, 'http://blackmarket.local')
    return url.pathname.slice(0, 200) || '/'
  } catch {
    return `/${value.split(/[?#]/, 1)[0].replace(/^\/+/, '').slice(0, 199)}`
  }
}

function safeText(value: string, limit = 240): string {
  return value
    .replace(/\b(?:https?|wss?):\/\/\S+/gi, '[URL]')
    .replace(/(authorization\s*[:=]\s*bearer\s+)[^\s,;]+/gi, '$1[REDACTED]')
    .replace(/(\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|credential|token)\b\s*[:=]\s*)[^\s,;]+/gi, '$1[REDACTED]')
    .slice(0, limit)
}

export function recordFrontendDiagnostic(
  input: Omit<FrontendDiagnosticEvent, 'id' | 'timestamp'>,
): FrontendDiagnosticEvent {
  const event: FrontendDiagnosticEvent = {
    ...input,
    id: `${Date.now().toString(36)}-${(++sequence).toString(36)}`,
    timestamp: new Date().toISOString(),
    operation: safeText(input.operation, 120),
    event: safeText(input.event, 120),
    endpoint: input.endpoint ? safeEndpoint(input.endpoint) : undefined,
    detail: input.detail ? safeText(input.detail) : undefined,
    recommendation: input.recommendation ? safeText(input.recommendation) : undefined,
    duration_ms: input.duration_ms != null && Number.isFinite(input.duration_ms)
      ? Math.max(0, input.duration_ms)
      : undefined,
  }
  events.push(event)
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS)
  pending.push(event)
  if (pending.length > MAX_PENDING_EVENTS) pending.splice(0, pending.length - MAX_PENDING_EVENTS)
  listeners.forEach((listener) => {
    try {
      listener(event)
    } catch {
      // Diagnostic subscribers must never interfere with the UI.
    }
  })
  return event
}

export function subscribeFrontendDiagnostics(
  listener: (event: FrontendDiagnosticEvent) => void,
): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getFrontendDiagnostics(): FrontendDiagnosticEvent[] {
  return [...events]
}

export function getPendingFrontendDiagnostics(limit = 50): FrontendDiagnosticEvent[] {
  return pending.slice(0, Math.max(0, limit))
}

export function acknowledgeFrontendDiagnostics(ids: string[]): void {
  const acknowledged = new Set(ids)
  for (let index = pending.length - 1; index >= 0; index -= 1) {
    if (acknowledged.has(pending[index].id)) pending.splice(index, 1)
  }
}

export async function traceFrontendOperation<T>(
  operation: string,
  action: () => Promise<T>,
): Promise<T> {
  const started = performance.now()
  try {
    const result = await action()
    recordFrontendDiagnostic({
      level: 'INFO',
      event: 'frontend_operation_completed',
      operation,
      status: 'SUCCESS',
      duration_ms: performance.now() - started,
    })
    return result
  } catch (error) {
    recordFrontendDiagnostic({
      level: 'ERROR',
      event: 'frontend_operation_failed',
      operation,
      status: 'FAILURE',
      duration_ms: performance.now() - started,
      detail: error instanceof Error ? error.message : 'Unexpected frontend operation failure.',
      recommendation: 'Inspect the operation details and correlated API request entries; retry after resolving the reported cause.',
    })
    throw error
  }
}
