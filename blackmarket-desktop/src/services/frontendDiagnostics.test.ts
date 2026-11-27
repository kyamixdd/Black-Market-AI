import assert from 'node:assert/strict'
import test from 'node:test'
import {
  acknowledgeFrontendDiagnostics,
  getFrontendDiagnostics,
  getPendingFrontendDiagnostics,
  recordFrontendDiagnostic,
  traceFrontendOperation,
} from './frontendDiagnostics.ts'

test('frontend diagnostics redact query strings and common secret assignments', () => {
  const event = recordFrontendDiagnostic({
    level: 'ERROR',
    event: 'request_failed',
    operation: 'GET /private',
    status: 'FAILURE',
    endpoint: '/private?token=secret-value',
    detail: 'request failed; api_key=secret-value',
  })

  test('frontend diagnostic endpoints keep only paths, including WebSocket URLs', () => {
    const event = recordFrontendDiagnostic({
      level: 'INFO',
      event: 'realtime_connected',
      operation: 'realtime.connect',
      status: 'SUCCESS',
      endpoint: 'wss://example.test/events/stream?token=private#fragment',
    })

    assert.equal(event.endpoint, '/events/stream')
  })

  assert.equal(event.endpoint, '/private')
  assert.equal(event.detail?.includes('secret-value'), false)
  assert.ok(getFrontendDiagnostics().some((entry) => entry.id === event.id))
})

test('frontend diagnostic batches can be acknowledged without removing the visible trace', () => {
  const event = recordFrontendDiagnostic({
    level: 'INFO',
    event: 'render_completed',
    operation: 'react.render.dashboard',
    status: 'SUCCESS',
  })

  assert.ok(getPendingFrontendDiagnostics().some((entry) => entry.id === event.id))
  acknowledgeFrontendDiagnostics([event.id])
  assert.equal(getPendingFrontendDiagnostics().some((entry) => entry.id === event.id), false)
  assert.ok(getFrontendDiagnostics().some((entry) => entry.id === event.id))
})

test('frontend operation trace records completion and preserves failures', async () => {
  await traceFrontendOperation('ui.load_success', async () => 'ok')
  await assert.rejects(traceFrontendOperation('ui.load_failure', async () => {
    throw new Error('test failure')
  }), /test failure/)

  const events = getFrontendDiagnostics()
  assert.ok(events.some((event) => event.operation === 'ui.load_success' && event.status === 'SUCCESS'))
  assert.ok(events.some((event) => event.operation === 'ui.load_failure' && event.status === 'FAILURE'))
})
