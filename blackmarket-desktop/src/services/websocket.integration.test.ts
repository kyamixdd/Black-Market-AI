import assert from 'node:assert/strict'
import test from 'node:test'
import { setApiToken } from './localAuth.ts'
import { WebSocketService } from './websocket.ts'

class MockSocket {
  static instances: MockSocket[] = []
  readyState = 0
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  sent: string[] = []
  constructor(public url: string) { MockSocket.instances.push(this) }
  send(value: string) { this.sent.push(value) }
  open() { this.readyState = 1; this.onopen?.({} as Event) }
  message(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent) }
  close() { this.readyState = 3; this.onclose?.({} as CloseEvent) }
}

test('WebSocket reconnects and authenticates again after a disconnect', async () => {
  const original = globalThis.WebSocket
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
  }
})
