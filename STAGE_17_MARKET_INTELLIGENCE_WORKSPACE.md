# Stage 17 — Unified Market Intelligence and Research Workspace

## Current implementation on this branch

### Market Regime Radar
- `market/regime_radar.py` adds a deterministic OHLCV-based classification using 20/50-period moving averages, 20-candle log-return realized volatility, and 20-candle slope.
- Labels include `UPTREND`, `DOWNTREND`, `RANGE_BOUND`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `MIXED`, and `INSUFFICIENT_DATA`.
- Each result includes UTC classification time, asset/market/timeframe, sample completeness, measured indicators, supporting evidence, and limitations.
- Rule-strength is not a calibrated probability; confidence is explicitly null or labeled as rule strength.
- API: `GET /api/intelligence/regime/{symbol}?market=SPOT&timeframe=1h&limit=100`.

### Evidence-backed market analysis
- API: `GET /api/intelligence/market-analysis/{symbol}?market=SPOT&timeframe=1h`.
- Separates observed snapshot values from calculated analytics, attaches the regime report, and returns supporting/conflicting evidence, risks, freshness, and invalidation conditions.
- No forecast or guaranteed outcome is generated.

### Strategy performance by regime
- `learning/regime_performance.py` calculates closed-trade count, net PnL, net return on summed trade notional, max trade-sequence drawdown, win rate, profit factor where defined, average holding time, and sample sufficiency.
- Strategy Lab reports now include `regime_performance`, using regime observations calculated only from completed candles before the trade entry timestamp to avoid lookahead.
- Insufficient samples are labeled; no forward-performance claim is made.

### AI trade review
- `learning/trade_review.py` builds a review from an actual closed paper-trade record and linked signal evidence.
- API: `GET /api/trades/{position_id}/review`.
- The endpoint reports the trade outcome separately from decision quality and tries to classify the market regime using candles before entry.
- Strategy rule adherence, position sizing, and risk-limit compliance are reported as `UNVERIFIABLE` unless the required historical execution/risk trace exists. This avoids manufacturing a positive or negative grade from P&L alone.

### Existing persistent research workspace
The existing `/api/research/workspaces` API persists schema-versioned workspace payloads in the application database. Existing research APIs also persist strategy definitions and backtest reports. The current ownership key is a single local owner; this is not multi-user isolation.

## Tests added

- `tests/test_stage17_regime_radar.py`
- `tests/test_stage17_regime_performance.py`
- `tests/test_stage17_trade_review.py`

These cover deterministic rules, insufficient/invalid data, regime sample grouping, net metrics, missing evidence, and outcome/decision-quality separation.

## Not complete / remaining Stage 17 work

This branch is a staged implementation, not the entire Stage 17 acceptance scope.

- No unified frontend workflow has been wired yet; desktop and hosted UI integration, synchronized asset/timeframe state, loading/error/freshness states, and responsive workflow remain.
- Workspace payloads are persisted, but typed watchlist/chart/indicator/alert models and UI restoration flow have not been completed or verified.
- Market breadth/correlation/scanner evidence is not yet fully consolidated into the new analysis response.
- Trade review cannot verify historical strategy-rule adherence or position sizing without persisted execution decision traces and risk snapshots. It explicitly marks these unknown.
- No full discovery-to-review end-to-end desktop or hosted browser test has been added yet.
- CI tests have not been executed from this branch at the time this document was authored.

## Verification command

```bash
pytest -q tests/test_stage17_regime_radar.py tests/test_stage17_regime_performance.py tests/test_stage17_trade_review.py
```

No real-money trading functionality is introduced.
