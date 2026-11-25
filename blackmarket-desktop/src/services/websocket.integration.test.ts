import assert from 'node:assert/strict'
import test from 'node:test'
import { setApiToken } from './localAuth.js'
import { WebSocketService } from './websocket.ts'

class MockSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: MockSocket[] = []
  readyState = 0
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  sent: string[] = []
  url: string
  constructor(url: string) { this.url = url; MockSocket.instances.push(this) }
  send(value: string) { this.sent.push(value) }
  open() { this.readyState = 1; this.onopen?.({} as Event) }
  message(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent) }
  close() { this.readyState = 3; this.onclose?.({} as CloseEvent) }
}

test('WebSocket reconnects and authenticates again after a disconnect', async () => {
  const original = globalThis.WebSocket
  const originalWindow = globalThis.window
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { __TAURI_INTERNALS__: {} } })
  MockSocket.instances = []
  globalThis.WebSocket = MockSocket as unknown as typeof WebSocket
  setApiToken('integration-token')
  const service = new WebSocketService()
  try {
    const connected = service.connect()
    const first = MockSocket.instances[0]
    first.open()
    first.message({ type: 'authenticated' })
    await connected
    first.close()
    await new Promise((resolve) => setTimeout(resolve, 1150))
    assert.equal(MockSocket.instances.length, 2)
    const second = MockSocket.instances[1]
    second.open()
    assert.ok(second.sent.some((raw) => JSON.parse(raw).type === 'authenticate'))
    second.message({ type: 'authenticated' })
    assert.equal(service.connectionState, 'connected')
  } finally {
    service.disconnect()
    setApiToken(null)
    globalThis.WebSocket = original
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow })
  }
})

class MockEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  static instances: MockEventSource[] = []
  readyState = 0
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  url: string
  constructor(url: string) { this.url = url; MockEventSource.instances.push(this) }
  open() { this.readyState = 1; this.onopen?.({} as Event) }
  fail() { this.readyState = 2; this.onerror?.({} as Event) }
  close() { this.readyState = 2 }
}

test('hosted SSE reconnects through the same-origin proxy after disconnect', async () => {
  const originalWindow = globalThis.window
  const originalEventSource = globalThis.EventSource
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {} })
  globalThis.EventSource = MockEventSource as unknown as typeof EventSource
  MockEventSource.instances = []
  const service = new WebSocketService()
  try {
    const connected = service.connect()
    const first = MockEventSource.instances[0]
    assert.equal(first.url, '/api/backend/events/stream')
    first.open()
    await connected
    first.fail()
    await new Promise((resolve) => setTimeout(resolve, 1150))
    assert.equal(MockEventSource.instances.length, 2)
    const second = MockEventSource.instances[1]
    assert.equal(second.url, '/api/backend/events/stream')
    second.open()
    assert.equal(service.connectionState, 'connected')
  } finally {
    service.disconnect()
    globalThis.EventSource = originalEventSource
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow })
  }
})
