import assert from 'node:assert/strict'
import test from 'node:test'
import { createBackendClient } from './backendClient.ts'

function response(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

test('desktop API requests attach bearer authentication and disable caching', async () => {
  let captured: { url: string; init?: RequestInit } | undefined
  const client = createBackendClient({
    baseUrl: 'http://127.0.0.1:8765/api',
    authorization: () => ({ Authorization: 'Bearer local-test-token' }),
    fetcher: async (url, init) => { captured = { url: String(url), init }; return response(200, { ok: true }) },
  })
  assert.deepEqual(await client.get('/portfolio/balance'), { ok: true })
  assert.equal(captured?.url, 'http://127.0.0.1:8765/api/portfolio/balance')
  assert.equal((captured?.init?.headers as Record<string, string>).Authorization, 'Bearer local-test-token')
  assert.equal(captured?.init?.cache, 'no-store')
})

test('startup failure is surfaced instead of returning placeholder data', async () => {
  const client = createBackendClient({
    baseUrl: '/api/backend',
    fetcher: async () => response(503, { detail: 'Local backend failed to start: database unavailable' }),
  })
  await assert.rejects(client.requestJson('http://127.0.0.1:8765/health'), /Local backend failed to start: database unavailable/)
})

test('portfolio refresh returns updated balance after paper order', async () => {
  let balance = 500
  const client = createBackendClient({
    baseUrl: '/api/backend',
    fetcher: async (url, init) => {
      if (String(url).endsWith('/trades') && init?.method === 'POST') {
        balance -= 25
        return response(200, { status: 'accepted', order_id: 'paper-1' })
      }
      if (String(url).endsWith('/portfolio/balance')) return response(200, { total_balance: balance })
      return response(404, { detail: 'Not found' })
    },
  })
  assert.deepEqual(await client.post('/trades', { symbol: 'BTCUSDT' }), { status: 'accepted', order_id: 'paper-1' })
  assert.deepEqual(await client.get('/portfolio/balance'), { total_balance: 475 })
})

test('rejected paper order retains backend rejection reason', async () => {
  const client = createBackendClient({
    baseUrl: '/api/backend',
    fetcher: async () => response(422, { detail: 'Insufficient available balance' }),
  })
  await assert.rejects(client.post('/trades', { symbol: 'BTCUSDT', quantity: 100000 }), /Insufficient available balance/)
})

test('API authentication failures are surfaced to the frontend', async () => {
  const client = createBackendClient({
    baseUrl: '/api/backend',
    authorization: () => undefined,
    fetcher: async (_url, init) => {
      const authorization = (init?.headers as Record<string, string> | undefined)?.Authorization
      return authorization ? response(200, { authenticated: true }) : response(401, { detail: 'Not authenticated' })
    },
  })
  await assert.rejects(client.get('/portfolio/balance'), /Not authenticated/)
})
