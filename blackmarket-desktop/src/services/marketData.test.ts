import assert from 'node:assert/strict'
import test from 'node:test'
import {
  assessMarketData,
  marketChartKey,
  mergeMarketCandles,
  parseMarketCandles,
} from './marketData.ts'

const now = Date.parse('2025-01-01T00:00:00Z')

function candle(open_time: number, close = 101) {
  return { open_time, open: 100, high: 102, low: 99, close, volume: 12 }
}

test('market data readiness requires a matching snapshot and valid candles', () => {
  const snapshot = {
    symbol: 'BTCUSDT',
    market: 'SPOT',
    price: 101,
    timestamp: new Date(now).toISOString(),
  }
  const candles = { candles: [candle(1_735_689_600_000)] }

  const missingSnapshot = assessMarketData(null, candles, 'BTCUSDT', 'SPOT', now)
  assert.equal(missingSnapshot.state, 'degraded')
  assert.equal(missingSnapshot.dataLoaded, false)
  assert.equal(assessMarketData(snapshot, null, 'BTCUSDT', 'SPOT', now).state, 'error')
  assert.equal(assessMarketData(snapshot, { candles: [] }, 'BTCUSDT', 'SPOT', now).state, 'error')
  assert.equal(assessMarketData(snapshot, candles, 'BTCUSDT', 'FUTURES', now).state, 'degraded')
  const ready = assessMarketData(snapshot, candles, 'BTCUSDT', 'SPOT', now)
  assert.equal(ready.state, 'ready')
  assert.equal(ready.dataLoaded, true)
})

test('candle parsing deduplicates and orders valid candles', () => {
  const parsed = parseMarketCandles({
    candles: [
      candle(3000),
      candle(1000),
      candle(1000, 100.5),
      { ...candle(2000), high: 90 },
    ],
  })

  assert.deepEqual(parsed.map((item) => item.time), [1000, 3000])
  assert.equal(parsed[0].close, 100.5)
})

test('historical merges remain sorted and do not duplicate timestamps', () => {
  const current = parseMarketCandles({ candles: [candle(2000), candle(3000)] })
  const merged = mergeMarketCandles(current, parseMarketCandles({ candles: [candle(1000), candle(2000, 100.5)] }))

  assert.deepEqual(merged.map((item) => item.time), [1000, 2000, 3000])
  assert.equal(merged[1].close, 100.5)
})

test('chart key changes for market type and timeframe switches', () => {
  const spot = marketChartKey('BTCUSDT', 'SPOT', '1h')
  assert.notEqual(spot, marketChartKey('BTCUSDT', 'FUTURES', '1h'))
  assert.notEqual(spot, marketChartKey('BTCUSDT', 'SPOT', '4h'))
})
