export type DiagnosticLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
export type DiagnosticEntry = {
  id: string
  timestamp: string
  level: DiagnosticLevel
  event: string
  error_type?: string
  feature?: string
  function?: string
  detail?: string
  duration_ms?: number
  trace_id?: string
  root_cause?: string
  suggested_fix?: string
  operation_id?: string
  result_summary?: string
}

const STORAGE_KEY = 'blackmarket-diagnostic-events-v1'
const MAX_ENTRIES = 1200
const MAX_BATCH = 80
const FRONTEND_TRACE_KEY = 'blackmarket-frontend-function-trace-v1'
let frontendFunctionTraceEnabled = false
let entries: DiagnosticEntry[] = []
let loaded = false
let installed = false
let activeScreen = 'Overview'

function redact(text: string): string {
  return text
    .replace(/(authorization\s*[:=]\s*bearer\s+)[^\s,;]+/gi, '$1[REDACTED]')
    .replace(/((?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|credential|token)\s*[:=]\s*)[^\s,;]+/gi, '$1[REDACTED]')
    .replace(/(https?:\/\/[^\s?#]+)[?#][^\s]*/gi, '$1?[REDACTED]')
    .slice(0, 1200)
}

function load(): void {
  if (loaded || typeof window === 'undefined') return
  loaded = true
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]') as DiagnosticEntry[]
    if (Array.isArray(value)) entries = value.slice(-MAX_ENTRIES)
  } catch {
    entries = []
  }
}

function persist(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)))
  } catch {
    // Keep the in-memory ring available if storage is full or disabled.
  }
}

export function recommendDiagnosticFix(error: unknown): { root_cause: string; suggested_fix: string } {
  const message = error instanceof Error ? error.message : String(error ?? 'Unknown error')
  const text = message.toLowerCase()
  if (text.includes('timeout') || text.includes('timed out')) return { root_cause: 'A request or dependency timed out.', suggested_fix: 'Check backend readiness, network/exchange latency and timeout settings; retry only idempotent operations.' }
  if (text.includes('network') || text.includes('fetch') || text.includes('connection')) return { root_cause: 'The frontend could not connect to the requested service.', suggested_fix: 'Check the desktop backend process, API address, connection status and local firewall.' }
  if (text.includes('401') || text.includes('403') || text.includes('unauthorized')) return { root_cause: 'The request was rejected by authentication or authorization.', suggested_fix: 'Check the authenticated desktop session and permission; do not bypass security checks.' }
  if (text.includes('429') || text.includes('rate limit')) return { root_cause: 'The request was rate-limited.', suggested_fix: 'Reduce polling/request frequency and honor retry/backoff headers.' }
  return { root_cause: 'The frontend operation failed; inspect the correlated request and stack details.', suggested_fix: 'Filter by trace_id/request_id, inspect the backend event immediately before this failure, and reproduce with the same screen and inputs.' }
}

export type FrontendFunctionTrace = { id: string; started: number; file: string; name: string } | null

export function getFrontendFunctionTraceEnabled(): boolean {
  if (typeof window === 'undefined') return frontendFunctionTraceEnabled
  try { frontendFunctionTraceEnabled = window.localStorage.getItem(FRONTEND_TRACE_KEY) === '1' } catch { /* Keep in-memory setting. */ }
  return frontendFunctionTraceEnabled
}

export function setFrontendFunctionTraceEnabled(enabled: boolean): void {
  frontendFunctionTraceEnabled = enabled
  try { window.localStorage.setItem(FRONTEND_TRACE_KEY, enabled ? '1' : '0') } catch { /* In-memory tracing still works. */ }
  recordDiagnostic('INFO', 'frontend.function_trace.changed', { feature: 'diagnostics', function: 'setFrontendFunctionTraceEnabled', detail: `enabled=${enabled}` })
}

export function traceFunctionStart(file: string, name: string): FrontendFunctionTrace {
  if (!getFrontendFunctionTraceEnabled()) return null
  const context = { id: crypto.randomUUID(), started: performance.now(), file: redact(file), name: redact(name) }
  recordDiagnostic('DEBUG', 'frontend.function.call', { feature: context.file, function: context.name, trace_id: context.id, detail: 'function entered' })
  return context
}

export function traceFunctionFailure(context: FrontendFunctionTrace, error: unknown): void {
  if (!context) return
  const message = error instanceof Error ? `${error.name}: ${error.message}\\n${error.stack ?? ''}` : String(error)
  recordDiagnostic('ERROR', 'frontend.function.failure', { feature: context.file, function: context.name, trace_id: context.id, duration_ms: Math.round(performance.now()-context.started), detail: redact(message), ...recommendDiagnosticFix(error) })
}

export function traceFunctionEnd(context: FrontendFunctionTrace, success: boolean): void {
  if (!context) return
  recordDiagnostic('DEBUG', 'frontend.function.complete', { feature: context.file, function: context.name, trace_id: context.id, duration_ms: Math.round(performance.now()-context.started), detail: success ? 'function completed' : 'function exited after exception' })
}

export function recordDiagnostic(
  level: DiagnosticLevel,
  event: string,
  fields: Omit<DiagnosticEntry, 'id' | 'timestamp' | 'level' | 'event'> = {},
): void {
  if (typeof window === 'undefined') return
  load()
  const entry: DiagnosticEntry = {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    level,
    event: redact(event),
    ...(fields.error_type ? { error_type: redact(fields.error_type) } : {}),
    ...(fields.feature ? { feature: redact(fields.feature) } : {}),
    ...(fields.function ? { function: redact(fields.function) } : {}),
    ...(fields.detail ? { detail: redact(fields.detail) } : {}),
    ...(typeof fields.duration_ms === 'number' ? { duration_ms: fields.duration_ms } : {}),
    ...(fields.trace_id ? { trace_id: redact(fields.trace_id) } : {}),
    ...(fields.root_cause ? { root_cause: redact(fields.root_cause) } : {}),
    ...(fields.suggested_fix ? { suggested_fix: redact(fields.suggested_fix) } : {}),
    ...(fields.operation_id ? { operation_id: redact(fields.operation_id) } : {}),
    ...(fields.result_summary ? { result_summary: redact(fields.result_summary) } : {}),
  }
  entries.push(entry)
  if (entries.length > MAX_ENTRIES) entries.splice(0, entries.length - MAX_ENTRIES)
  persist()
}

export function getDiagnosticLogSnapshot(): DiagnosticEntry[] {
  load()
  return entries.slice()
}

export function setDiagnosticScreen(screen: string): void {
  if (screen === activeScreen) return
  const previous = activeScreen
  activeScreen = screen
  recordDiagnostic('INFO', 'screen.changed', { feature: screen, detail: `${previous} → ${screen}` })
}

export function installDiagnosticCapture(): void {
  if (installed || typeof window === 'undefined') return
  installed = true
  load()
  recordDiagnostic('INFO', 'frontend.diagnostics.started', { feature: 'diagnostics', detail: 'Frontend error and interaction capture installed' })
  window.addEventListener('error', (event) => {
    recordDiagnostic('ERROR', 'frontend.window.error', {
      feature: activeScreen, function: event.filename ? event.filename.split('/').pop() : 'window.onerror',
      detail: `${event.message} at line ${event.lineno}:${event.colno}`,
    })
  })
  const originalConsoleWarn = console.warn.bind(console)
  const originalConsoleError = console.error.bind(console)
  console.warn = (...args: unknown[]) => {
    try {
      recordDiagnostic('WARNING', 'frontend.console.warn', {
        feature: activeScreen, function: 'console.warn',
        detail: args.map((arg) => arg instanceof Error ? `${arg.name}: ${arg.message}` : typeof arg === 'string' ? arg : Object.prototype.toString.call(arg)).join(' ').slice(0, 1000),
      })
    } catch { /* Diagnostic capture must not affect the console. */ }
    originalConsoleWarn(...args)
  }
  console.error = (...args: unknown[]) => {
    try {
      recordDiagnostic('ERROR', 'frontend.console.error', {
        feature: activeScreen, function: 'console.error', ...recommendDiagnosticFix(args.find((arg) => arg instanceof Error) ?? args.join(' ')),
        detail: args.map((arg) => arg instanceof Error ? `${arg.name}: ${arg.message}\n${arg.stack ?? ''}` : typeof arg === 'string' ? arg : Object.prototype.toString.call(arg)).join(' ').slice(0, 1000),
      })
    } catch { /* Diagnostic capture must not affect the console. */ }
    originalConsoleError(...args)
  }
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error ? `${event.reason.name}: ${event.reason.message}\n${event.reason.stack ?? ''}` : String(event.reason)
    recordDiagnostic('ERROR', 'frontend.unhandled_rejection', { feature: activeScreen, function: 'promise', detail: reason, ...recommendDiagnosticFix(reason) })
  })
  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target.closest('button,[role="button"],a,[data-diagnostic-feature]') : null
    if (!target) return
    const label = target.getAttribute('aria-label') ?? target.getAttribute('title') ?? target.getAttribute('data-diagnostic-feature') ?? target.textContent?.trim().slice(0, 80) ?? target.tagName
    recordDiagnostic('DEBUG', 'ui.interaction', { feature: activeScreen, function: 'click', detail: `${target.tagName.toLowerCase()} · ${label}` })
  }, true)
  document.addEventListener('submit', (event) => {
    const form = event.target instanceof HTMLFormElement ? event.target : null
    if (!form) return
    recordDiagnostic('INFO', 'ui.form.submit', { feature: activeScreen, function: 'submit', detail: form.getAttribute('aria-label') ?? form.className.toString().slice(0, 100) })
  }, true)
  window.setInterval(() => { void flushDiagnosticLogs() }, 1000)
}

export async function flushDiagnosticLogs(): Promise<void> {
  load()
  const batch = entries.filter((entry) => !entry.id.startsWith('sent:')).slice(-MAX_BATCH)
  if (!batch.length || typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) return
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const token = await invoke<string>('backend_api_token')
    const events = batch.map((entry) => ({
      level: entry.level,
      event: entry.event,
      timestamp: entry.timestamp,
      feature: entry.feature,
      function: entry.function,
      detail: entry.detail,
      duration_ms: entry.duration_ms,
      trace_id: entry.trace_id,
    }))
    const response = await fetch('http://127.0.0.1:8765/api/diagnostics/frontend-events', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ events }),
    })
    if (!response.ok) return
    const sent = new Set(batch.map((entry) => entry.id))
    entries = entries.map((entry) => sent.has(entry.id) ? { ...entry, id: `sent:${entry.id}` } : entry)
    persist()
  } catch {
    // Local diagnostics remain available when the backend is offline.
  }
}

export function clearDiagnosticLogs(): void {
  entries = []
  loaded = true
  persist()
}
