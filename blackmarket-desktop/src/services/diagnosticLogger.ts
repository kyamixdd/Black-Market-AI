export type DiagnosticLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
export type DiagnosticEntry = {
  id: string
  timestamp: string
  level: DiagnosticLevel
  event: string
  feature?: string
  function?: string
  detail?: string
  duration_ms?: number
  trace_id?: string
}

const STORAGE_KEY = 'blackmarket-diagnostic-events-v1'
const MAX_ENTRIES = 1200
const MAX_BATCH = 80
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
    ...(fields.feature ? { feature: redact(fields.feature) } : {}),
    ...(fields.function ? { function: redact(fields.function) } : {}),
    ...(fields.detail ? { detail: redact(fields.detail) } : {}),
    ...(typeof fields.duration_ms === 'number' ? { duration_ms: fields.duration_ms } : {}),
    ...(fields.trace_id ? { trace_id: redact(fields.trace_id) } : {}),
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
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error ? `${event.reason.name}: ${event.reason.message}\n${event.reason.stack ?? ''}` : String(event.reason)
    recordDiagnostic('ERROR', 'frontend.unhandled_rejection', { feature: activeScreen, function: 'promise', detail: reason })
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
  window.setInterval(() => { void flushDiagnosticLogs() }, 5000)
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
