# Stage 4 — Market Data Reliability Layer

## Scope and implementation

Implemented on `stage-4/market-data-reliability`, based on `black-market-ai-beta`. Existing Binance public Spot and USDⓈ-M Futures clients and scanner remain in place.

- Added `market/data_reliability.py` with symbol, price, volume, and OHLCV validation; a stable freshness state enum/record; source and timestamp tracking; and a bounded LRU TTL cache primitive.
- `CandleManager` now rejects unsupported markets/timeframes, malformed/non-finite or invalid OHLCV values, invalid/future timestamps, and duplicate open times. Updates to an existing candle require a non-older close timestamp. Series remain bounded and sorted.
- Fixed recent candle gap detection to compare chronological neighbors and report every missing interval, rather than incorrectly comparing reverse-ordered candle indexes.
- REST clients now cap concurrent requests, use bounded retries for transport errors, HTTP 429/418 and 5xx, honor `Retry-After` when parseable, and apply exponential backoff with jitter. Public GET-only provider architecture is unchanged.
- Market ticker cache validates values, records source (`REST` or `WEBSOCKET`), and exposes aggregate `LIVE`, `DELAYED`, `STALE`, or `UNAVAILABLE` freshness.
- Scanner validates REST and stream ticker values before caching. Stream events outside the accepted exchange timestamp window are discarded.
- Added `/api/markets/data-status` to report Spot/Futures freshness/source plus WebSocket stream status.
- WebSocket manager exposes connection status, last-message age, reconnect attempts, and subscribed stream count; existing reconnect/backoff and scanner REST polling remain.
- Added offline tests for data validation, malformed candles, duplicate candle handling, gaps, ordering/bounds, freshness state, cache expiry/capacity, source metadata, and WebSocket state.

## Existing architecture retained

Binance public REST polling remains the fallback and continues on the scanner's existing cycle. WebSocket subscriptions remain bounded to the configured liquid-symbol limit; the scanner rotates REST candle analysis through eligible symbols and configured timeframes. This change does not increase subscriptions to every symbol/timeframe.

## Validation status

Automated tests were added to the backend test suite. CI is required to confirm Python regression tests, static checks, and desktop/web builds. No live Binance requests are required by the new reliability tests. No deployment or production configuration was changed.

## Known limits / follow-up

- Binance REST rate limits are weight-based and endpoint-specific. The limiter provides conservative request-level ceilings and bounded concurrency/retries; exact per-endpoint weight accounting and response-header weight budgeting still require further work.
- WebSocket health is aggregate across configured stream connections. Market ticker source is retained per symbol; exact exchange event time is not yet persisted in the ticker cache, so the status API reports `last_exchange_event` as null there. WebSocket manager separately reports the most recent received message time.
- The TTL cache primitive is available and tested, but this stage does not wrap every historical endpoint in a shared cache or implement incremental indicator calculation across all consumers.
- REST polling is the automatic fallback path; it does not prove a live WebSocket connection. Status explicitly distinguishes stream state and per-market REST/stream freshness.
