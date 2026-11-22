# Stage 5 — Market Analytics and Scanner

## Scope
Branch: `stage-5/market-analytics-scanner`
Base: `black-market-ai-beta`

This stage audits the metrics in the backend bridge and market panels, corrects misleading sample semantics, adds deterministic analytics helpers and API endpoints, and improves scanner coverage/failure reporting. No live exchange data is used by the new deterministic tests.

## Metric audit

### Implemented with a defined source/calculation
- Exchange ticker 24-hour price change and rolling quote volume: provider 24-hour ticker fields.
- Futures funding rate and open interest: public USDⓈ-M Futures endpoints; open interest value is contracts multiplied by mark price.
- RSI, MACD, moving averages, Bollinger Bands, ATR, VWAP, volume trend and expansion: candle-derived indicators, subject to required candle history.
- 24-hour realized volatility: 24 close-to-close logarithmic returns from 25 completed hourly candles; reported as realized volatility over the interval, not annualized.
- ATR: true-range average normalized by latest close; the snapshot method uses completed hourly candles.
- 7-day quote-volume comparison: current rolling 24-hour quote volume against the mean of exactly 7 completed UTC daily quote-volume candles.
- Advance/decline/neutral breadth: cached eligible ticker sample, now separated into Spot and Futures.
- Relative strength: each ticker's 24-hour change minus the mean 24-hour change of cached eligible tickers in the same market. It is a relative-to-sample measure, not a benchmark index.
- Asset correlation: new endpoint calculates Pearson correlation of aligned close-to-close logarithmic returns and requires at least 20 aligned returns.

### Partial / sample-limited / unavailable
- Aggressor buy/sell flow: sum of buyer/seller-initiated quote value from the last 500 aggregate trades. It is explicitly a sample and is not a full 24-hour buy/sell volume profile.
- Seven-day buy/sell volume averages: unavailable; not inferred from daily candles or the limited aggregate-trade sample. API fields remain null.
- Order-book depth, spread and imbalance: unavailable in aggregate breadth because no live order-book sample is populated. These fields return null with explanatory status rather than fabricated zero.
- Liquidation flow: not implemented in the reviewed public market analytics contract.
- Market breadth coverage: cached eligible market listings, not the entire exchange at every instant. Spot and Futures are counted separately; the same underlying asset can appear in both.
- Price change intervals: new endpoint reports 1h, 24h and 7d close-to-close changes from the requested candle timeframe, with null when the required interval is not present.
- Data completeness: new analytics endpoint includes completed candle count, required counts and per-interval readiness. Scanner status exposes configured timeframes, batch size and per-market refresh outcome.

### Previously misleading or incomplete behavior corrected
- Trend analysis previously accepted 50 candles while using SMA200, which silently fell back to the latest close. Trend analysis now requires 200 candles and reports available/required candle counts and completeness.
- ADX previously returned a single DX value labeled ADX. It now uses Wilder smoothing and an ADX initialization window.
- RSI on a flat series previously returned 100; it now returns 50 when both average gain and average loss are zero.
- Volume panel previously compared sampled buyer/seller flow against full rolling 24-hour volume and could call unavailable fields with `toFixed`. It now displays the sample explicitly and handles nulls/errors.
- Breadth panel previously called `toFixed` on null spread/imbalance values and combined Spot/Futures counts. It now separates markets and labels depth metrics unavailable.
- Candle insertion now rejects invalid OHLCV, unsupported market/timeframe, invalid symbol and future timestamp values; candle gap detection checks chronological intervals.

## Scanner behavior
- Uses the configured `TIMEFRAMES` and bounded per-market symbol batch.
- With scan-all enabled, rotates across the eligible ticker universe without slicing beyond the available candidates; each selected symbol is refreshed across all configured timeframes.
- Candle requests remain bounded by the configured concurrency semaphore.
- Collection errors are recorded per market/symbol/timeframe and isolated; one failed request does not cancel the other refreshes.
- Scanner status endpoint: `GET /api/markets/scanner-status`.
- Status includes configured timeframes, batch size, scan-all setting, stream limit, selected symbols, successful/failed candle refreshes, completion time and degraded/complete state.
- Candle collector records success/failure, duration, returned candle count and changed candle count.

## New endpoints
- `GET /api/markets/analytics/{symbol}?market=SPOT&timeframe=1h`
- `GET /api/markets/correlation?symbol_a=BTCUSDT&symbol_b=ETHUSDT&market=SPOT&timeframe=1h&limit=200`
- `GET /api/markets/scanner-status`

## Tests
Added deterministic tests for:
- Realized volatility exact sample boundary and invalid prices.
- Volume baseline, zero-volume and insufficient-history behavior.
- Price-change period boundaries.
- Correlation of aligned returns and constant series.
- Breadth counts and unavailable sample.
- Candle OHLC validation and missing intervals.
- Wilder ADX initialization and directional behavior.

CI must run the Python regression suite and desktop/web type/build checks before this draft is considered merge-ready.

## Remaining limitations
- The 7-day comparison is based on daily quote-volume candles; it is not a seven-day buyer/seller aggressor flow breakdown.
- The correlation endpoint is available to the frontend/API, but no dedicated correlation visualization was added in this stage.
- Full live order-book sampling, historical liquidation data, and exchange-wide breadth completeness remain outside this stage.
- Scanner coverage is bounded and rotating when the eligible universe exceeds the configured batch; the status endpoint reports batch configuration and most recent scan outcomes rather than claiming every symbol/timeframe was refreshed in a single cycle.
