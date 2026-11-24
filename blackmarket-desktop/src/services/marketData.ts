export type MarketCandle = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume?: number
  closeTime?: number
}

export type MarketDataState = 'loading' | 'ready' | 'degraded' | 'disconnected' | 'error'

export type MarketSnapshotData = {
  symbol: string
  market: string
  timestamp?: string | number | null
  price: number
  price_change_24h?: number | null
  volume_24h?: number | null
  regime?: string
  bid_ask_spread?: number | null
  orderbook_imbalance?: number | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isMarketSnapshot(value: unknown): value is MarketSnapshotData {
  return isRecord(value)
    && typeof value.symbol === 'string'
    && typeof value.market === 'string'
    && finiteNumber(value.price)
    && value.price > 0
    && (value.timestamp === undefined || value.timestamp === null || typeof value.timestamp === 'string' || finiteNumber(value.timestamp))
    && (value.price_change_24h === undefined || value.price_change_24h === null || finiteNumber(value.price_change_24h))
    && (value.volume_24h === undefined || value.volume_24h === null || finiteNumber(value.volume_24h))
    && (value.regime === undefined || typeof value.regime === 'string')
    && (value.bid_ask_spread === undefined || value.bid_ask_spread === null || finiteNumber(value.bid_ask_spread))
    && (value.orderbook_imbalance === undefined || value.orderbook_imbalance === null || finiteNumber(value.orderbook_imbalance))
}

export function parseMarketCandles(payload: unknown): MarketCandle[] {
  if (!isRecord(payload) || !Array.isArray(payload.candles)) return []

  const candles = new Map<number, MarketCandle>()
  for (const item of payload.candles) {
    if (!isRecord(item)) continue
    const rawTime = finiteNumber(item.open_time) ? item.open_time : item.time
    const open = item.open
    const high = item.high
    const low = item.low
    const close = item.close
    const volume = item.volume
    const closeTime = item.close_time
    if (
      !finiteNumber(rawTime)
      || !finiteNumber(open)
      || !finiteNumber(high)
      || !finiteNumber(low)
      || !finiteNumber(close)
      || rawTime <= 0
      || open <= 0
      || low <= 0
      || close <= 0
      || high < Math.max(open, close, low)
      || low > Math.min(open, close)
      || (volume !== undefined && volume !== null && (!finiteNumber(volume) || volume < 0))
      || (closeTime !== undefined && closeTime !== null && !finiteNumber(closeTime))
    ) continue

    const time = rawTime > 10_000_000_000 ? Math.floor(rawTime / 1000) : rawTime
    candles.set(time, {
      time,
      open,
      high,
      low,
      close,
      volume: finiteNumber(volume) ? volume : undefined,
      closeTime: finiteNumber(closeTime) ? closeTime : undefined,
    })
  }
  return [...candles.values()].sort((left, right) => left.time - right.time)
}

export function mergeMarketCandles(
  current: MarketCandle[],
  incoming: MarketCandle[],
  maximum = 5000,
): MarketCandle[] {
  const candles = new Map(current.map((candle) => [candle.time, candle]))
  for (const candle of incoming) candles.set(candle.time, candle)
  return [...candles.values()]
    .sort((left, right) => left.time - right.time)
    .slice(-maximum)
}

export function marketChartKey(symbol: string, market: string, timeframe: string): string {
  return `${symbol}:${market}:${timeframe}`
}

export function assessMarketData(
  snapshot: unknown,
  candleResponse: unknown,
  symbol: string,
  market: string,
  now = Date.now(),
): {
  state: MarketDataState
  candles: MarketCandle[]
  snapshot: MarketSnapshotData | null
  dataLoaded: boolean
} {
  const candles = parseMarketCandles(candleResponse)
  const candlePayloadValid = isRecord(candleResponse) && Array.isArray(candleResponse.candles)
  if (!candlePayloadValid || candles.length === 0) {
    return { state: 'error', candles: [], snapshot: null, dataLoaded: false }
  }

  const snapshotValid = isMarketSnapshot(snapshot)
    && snapshot.symbol === symbol
    && snapshot.market === market
  if (!snapshotValid) {
    return { state: 'degraded', candles, snapshot: null, dataLoaded: false }
  }

  const timestamp = snapshot.timestamp
  const snapshotTime = typeof timestamp === 'number'
    ? (timestamp > 10_000_000_000 ? timestamp : timestamp * 1000)
    : typeof timestamp === 'string' ? Date.parse(timestamp) : Number.NaN
  if (!Number.isFinite(snapshotTime) || now - snapshotTime > 120_000 || snapshotTime > now + 5_000) {
    return { state: 'degraded', candles, snapshot, dataLoaded: true }
  }
  return { state: 'ready', candles, snapshot, dataLoaded: true }
}
