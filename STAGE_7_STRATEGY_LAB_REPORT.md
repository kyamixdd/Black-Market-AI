# Stage 7 — Strategy Lab and Historical Backtesting

## Scope
Adds a research-only historical simulation workflow that reuses the existing five strategy implementations. No live exchange order execution is added.

## Added
- Deterministic backtest runner in `learning/strategy_lab.py`.
- POST endpoints `/api/learning/strategy-lab` and `/api/learning/strategy-lab/compare`.
- Strategy Lab dashboard screen with strategy, symbol, market, timeframe, date range, starting capital, risk/fixed-notional sizing, maximum position, minimum strategy score, and optional fee/spread/slippage overrides.
- Same-condition comparison for all five registered strategies.
- Per-trade records, equity curve, return/cost metrics, drawdown, profit factor, win rate, average win/loss, reward-to-risk proxy, Sharpe, exposure and buy-and-hold benchmark.
- Deterministic fixtures in `tests/test_strategy_lab_stage7.py`.

## Execution model
- Signals use only completed candles up to the decision bar.
- Entries fill at the following bar's open.
- Stop-loss and take-profit checks use historical OHLC. If both are touched in one bar, stop-loss is assumed first.
- Stop-loss gaps are filled at the open when that is worse than the stop price.
- Taker fees, spread and slippage are applied to entry and exit. Costs are reported separately and are not double-counted in gross P&L.
- Position sizing supports risk-per-trade percentage and fixed notional, capped by maximum position as a percentage of equity.
- Equity is marked to market during open positions for drawdown calculation.
- Duplicate candle timestamps are deduplicated and invalid candles are excluded.

## Historical data
The API fetches selected date-range candles through the existing Binance public clients in bounded backward pages (up to 20 pages; 20,000 Spot or 30,000 Futures candles). The current candle provider/cache is not a durable full-history archive.

## Metrics and limitations
- Sharpe is annualized from daily realized net returns using `sqrt(365)`; unavailable when the sample is insufficient or variance is zero.
- Benchmark is buy-and-hold over the same candle range, without benchmark transaction costs.
- Exposure is based on bars held relative to the equity-curve bars.
- Strategy parameter interface currently exposes the common minimum raw strategy score. Existing strategy classes do not yet define a generic parameter schema.
- Futures funding can be modeled with an explicit funding-rate assumption. Historical funding-rate series are not currently fetched/replayed, so the default is no funding charge and the UI does not claim historical funding accuracy.
- Exchange-specific tiered fees, market impact, partial fills, and precise intrabar order sequencing are not modeled. Backtests are research estimates, not profitability evidence.

## Verification
CI and type/build checks are pending for this branch. Stage 7 is not ready to merge until the new deterministic tests and existing regression suites pass.
