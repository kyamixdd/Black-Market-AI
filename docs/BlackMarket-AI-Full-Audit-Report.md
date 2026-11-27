# BlackMarket AI — Full-Stack Audit Report
**Audit Date:** 26 November 2026  
**Version:** 1.0.0 (branch `Black-Market-AI-Beta-1.0.1`, baseline commit `466dbc7`, working tree has uncommitted changes)  
**Audit Scope:** Every source file across all layers — Python engines, FastAPI backend, assistant AI, Tauri Rust shell, React/TS frontend, database, exchange, monitoring, build/CI.  
**Classification:** 🟡 Functional Beta — NOT ready for unrestricted public release

---

## Executive Summary

BlackMarket AI is a large, ambitious local-first crypto market research and paper-trading platform. The codebase demonstrates strong architectural intent — fail-closed designs, atomic persistence, promotion gates, CSP, loopback auth — but a full line-by-line audit reveals **multiple critical runtime bugs that prevent core features from working end-to-end**, along with broken ML pipelines, disconnected monitoring, dead UI code, and several release-blocking security/safety findings.

| Layer | Health | Notes |
|---|:---:|---|
| **Test Suite** | 🟢 684/684 | All pass (3 live-exchange skips, 1 deprecation warning) |
| **Desktop Lint/Build** | 🟢 Pass | 0 lint errors, 23/23 service tests, 1 chunk size warning |
| **Tauri Rust Tests** | 🟢 6/6 | Log-tail, redaction, health probe all pass |
| **FastAPI Backend & Auth** | 🟡 Mostly Working | 4 critical bugs found (NameError, bad evidence map, inf JSON, ASCII guard) |
| **Assistant Pipeline** | 🟡 Mostly Working | 4/14 NLU benchmark intent failures; multi-tool provider skip |
| **Core Orchestrator** | 🔴 Partially Broken | Telegram blocks EventBus; stale attributes break terminal; EventBus persistence can crash bus |
| **ML / Learning Pipeline** | 🔴 Largely Broken | Scaler mismatch, live retraining always blocked, backtester generates 0 trades |
| **Paper Trading Simulator** | 🟡 Mostly Working | Partial-close audit math wrong; 3 methods lack account lock |
| **Risk Engine** | 🔴 Not Connected | AdaptiveRiskEngine never instantiated; cooldown permanently pauses entries |
| **Exchange / Market Data** | 🟡 Mostly Working | MIN_NOTIONAL filter parsing inaccurate; WS restart drops both markets |
| **Database** | 🟡 Mostly Working | Duplicate `save_candles`, duplicate-event IntegrityError, N+1 queries, missing indexes |
| **Monitoring (DriftMonitor)** | 🔴 Disconnected | Never instantiated; counting per-call not per-day |
| **Terminal Dashboard** | 🔴 Largely Broken | Wrong attribute names, wrong Textual API, hardcoded balances |
| **Desktop Frontend (React)** | 🟡 Mostly Working | WebSocket push callbacks never fire; dead/unused legacy components |
| **Build / CI** | 🟡 Mostly OK | START_BLACKMARKET.bat missing dev config; double-bundled PyInstaller |

---

## Test Suite Results (Verified in This Audit)

| Suite | Command | Result |
|---|---|---|
| Python backend | `pytest -q -m "not live"` | **684 passed**, 3 deselected, 1 Starlette/httpx deprecation warning |
| Desktop service tests | `npm test` | **23/23 passed** |
| Desktop lint | `oxlint` (28 files, 116 rules) | **0 warnings, 0 errors** |
| Desktop build | `npm run build` (vite) | **Pass** — 1 chunk >500 KB warning (`index-*.js` ~578 KB gzip ~174 KB) |
| Rust supervisor tests | `cargo test --lib` | **6/6 passed** |

> [!NOTE]
> Tests passing confirms the _unit-level_ behaviour is correct. It does not verify end-to-end ML retraining, live Binance streams, clean-machine installer behaviour, or the runtime bugs documented below.

---

## 1. FastAPI Backend & Routes (`src_tauri/backend/`)

### 1.1 What Works Well
- **Auth & Loopback** (`main.py:289–322`): `require_local_api_auth` fails closed — 503 when token is unset, 401 on bad bearer, 403 on non-loopback when remote mode is off.
- **WebSocket Auth** (`main.py:392–444`): 5-second `{"type":"authenticate","token":...}` handshake with `hmac.compare_digest`, per-IP rate limiting (30/window), loopback enforcement.
- **SSE Stream** (`main.py:348–389`): Bounded 512-item queue; drop-oldest on saturation.
- **Trade/Position Validation** (`trades.py`, `positions.py`): Finite positive prices, directional SL/TP invariants, risk-sized max quantity, Spot-long-only rules, rollback on persistence failure.
- **Assistant Tool Safety**: All 11 tools are `read_only=True`, schema-validated, timeout-bounded (15s). SSRF guard checks HTTPS or exact loopback for provider URLs.
- **Benchmark Governance** (`benchmarks/assistant_outcomes/`): Transparently documents 4 failing NLU intents; baseline marked ineligible for promotion.

### 1.2 Critical Bugs

**🔴 BUG 1 — `NameError` crash on `GET /api/assistant/tools`**  
`src_tauri/backend/api/routes/assistant.py:97–100` calls `create_default_registry()` which is **never imported**. Every call to this endpoint raises `NameError` and returns HTTP 500.  
**Fix:** Add `from src_tauri.backend.assistant_tool_registry import create_default_registry` to `assistant.py`.

**🔴 BUG 2 — Market Analysis evidence payload is always empty**  
`src_tauri/backend/api/routes/intelligence.py:105–109` filters analytics for keys `("price_changes", "indicators", "data_completeness", "status")`, but `bridge.get_symbol_analytics()` returns `"price_change_pct"`, `"historical_volatility_24h_pct"`, `"atr_14_pct"`, `"volume_vs_prior_20_candles"`, `"completed_candle_count"`, `"required_candles"`, `"data_completeness"`. All price/indicator evidence is stripped from every response.  
**Fix:** Update the key allowlist in `intelligence.py:105–109` to match the actual bridge output keys.

**🔴 BUG 3 — JSON serialization crash on `profit_factor = float('inf')`**  
`orchestrator_bridge.py:592` sets `profit_factor = float('inf')` when `gross_loss == 0 and gross_profit > 0`. Standard JSON encoding raises `ValueError: Out of range float values are not JSON compliant`.  
**Fix:** Replace `float('inf')` with `None` and type `profit_factor: float | None` in the response schema.

**🔴 BUG 4 — `TypeError` on non-ASCII `Authorization` in `/_internal/shutdown`**  
`main.py:497` uses `hmac.compare_digest(supplied_token, _shutdown_token)` without the `.isascii()` guard used in `_matches_bearer_token` (`L100`). A non-ASCII Authorization header raises an uncaught `TypeError` → HTTP 500.  
**Fix:** Add `if not supplied_token.isascii(): raise HTTPException(401)` before the `compare_digest` call.

### 1.3 Medium Bugs & Gaps

| ID | Location | Issue |
|---|---|---|
| M-1 | `api/schemas.py` | Entirely unused dead-code module; also defines `MarketHeatmapResponse` twice and `SignalResponse.timeframe` twice |
| M-2 | `trades.py:82`, `learning.py:34`, `activity.py:13` | `limit` params have `le=1000` but no `ge=1`; negative limit causes `[-limit:]` to slice from front |
| M-3 | `research.py` DELETEs | Missing ID regex validation present on GET/PUT counterparts |
| M-4 | `community.py` | `update_strategy`, `unpublish_strategy`, `favorite_strategy`, `report_strategy` omit `public_id` hex validation |
| M-5 | `assistant.py:107` | `AssistantQuery.market` checks length instead of `^(SPOT\|FUTURES)$`; `symbol` lacks `^[A-Z0-9]+$` |
| M-6 | `learning.py:212,304`, `evolution.py:26` | Accept untyped `dict` payloads with no Pydantic schema or size limit |
| M-7 | Across 7 modules | Timeframe allowlists diverge (15 / 12 / 9 variants) — no shared constant |
| M-8 | `main.py:224` | `_request_buckets` dict grows unboundedly per unique client IP |
| M-9 | `orchestrator_bridge.py:34,35` | `_candle_refresh_at` and `_analytics_cache` have no max-size eviction |
| M-10 | `websocket/manager.py:104–116` | `shutdown()` never unsubscribes `_on_event` from EventBus |
| M-11 | `websocket/manager.py` | `_on_event` awaits `_send()` sequentially — a slow client can block the entire EventBus |
| M-12 | `main.py:481` | `/health` hardcodes `"paper_trading_active": True` once backend is up |
| M-13 | `orchestrator_bridge.py:643` | `get_strategy_weights()` hardcodes `"BULL_TREND"` regime preference |
| M-14 | `backup.py:24–39` | Instantiates a new `Database` and calls `init_db()` on every backup request |
| M-15 | `main.py:395` | `/ws` blocks non-loopback even when `BLACKMARKET_REMOTE_API_ENABLED=1` |
| M-16 | `community.py:25–28` | Community identity trusts any 36-char UUID in `X-BM-Community-Owner` without binding to auth |
| M-17 | `assistant_runtime.py:166` | Provider interpretation skipped when `len(successful) != 1` (multi-tool queries never get LLM summary) |
| M-18 | `assistant_memory.py:70` | Only fetches 20 SQLite rows before scoring — older relevant memories are invisible |

### 1.4 Assistant / NLU (4 Benchmark Failures)

| Test | Input | Failure |
|---|---|---|
| intent-004 | "Check the market scanner" | Matches `market_snapshot` instead of `scanner_status` |
| intent-009 | "Show recent trade history" | Matches `historical_candles` instead of `trade_history` |
| intent-010 | "What is my portfolio risk exposure" | Matches `paper_account` instead of `risk_status` |
| intent-013 | "Analyze it again" | Matches `market_snapshot` instead of returning clarification |

---

## 2. Core Orchestrator & Infrastructure (`core/`)

### 2.1 What Works Well
- Atomic file persistence in `runtime_settings_store.py`, `daily_equity_state.py`, `controlled_evolution.py` (mkstemp + fsync + os.replace + 0o600 permissions).
- `_live_paper_confidence_gate` (`orchestrator.py:460–576`): Fail-closed — checks registry match, calibrated threshold, snapshot staleness, closed candle counts, finite features, directional agreement.
- `DatabaseBackupManager.restore_backup`: Validates checksums, `PRAGMA integrity_check`, WAL checkpoint, staged rollback copy, atomic restore of DB + `runtime_settings.json`.
- `PositionRecoveryManager._recover_balances`: Accurately rebuilds P&L, reserved notional/margin, fees, and same-day equity baseline.

### 2.2 Bugs & Issues

**🔴 BUG — EventBus persistence failure kills the bus loop**  
`core/event_bus.py:80–81`: If `self._persist(event)` raises, the exception propagates outside the inner `try/except` and exits `run()`, stopping all event processing permanently.  
**Fix:** Wrap `_persist(event)` in its own `try/except Exception` block.

**🔴 BUG — Telegram awaits block EventBus dispatch**  
`core/orchestrator.py:593–615, 777–778, 822–823, 868–892`: Multiple `await self.telegram.*` calls are executed synchronously inside `EventBus.run()`. Any Telegram network timeout stalls all market, signal, and order event processing.  
**Fix:** Dispatch all Telegram calls to a bounded background `asyncio.Queue` worker via `asyncio.create_task`.

**🔴 BUG — Duplicate AUTODEC event IDs → `IntegrityError`**  
`core/orchestrator.py:692`: `event_id = f"AUTODEC-{signal_id}-{status}"[:64]` + `session.add(ev)`. Re-evaluating the same signal with the same status crashes persistence with `IntegrityError`.  
**Fix:** Use `INSERT OR IGNORE` or `session.merge()` in `Repository.save_system_event`.

| ID | Location | Issue |
|---|---|---|
| C-1 | `orchestrator.py:100–104` | `_scanning`, `_ws_connected`, `_tracked_symbols`, `_recent_snapshots`, `_current_regime` initialized but never updated — breaks terminal dashboard |
| C-2 | `event_bus.py:107–110` | `stop()` → `queue.join()` hangs forever if `run()` never started |
| C-3 | `orchestrator.py:1094` | `async def handle_signal` cannot be registered with `signal.signal()` |
| C-4 | `orchestrator.py:780–786` | `_on_market_data` calls `update_prices()` but never `check_limit_orders()` |
| C-5 | `scheduler.py:16–24` | `_wrapper()` exits immediately if task starts before `start()` is awaited; `Scheduler` itself is unused |
| C-6 | `disaster_recovery.py` | `PersistentEventQueue.dequeue()` is a stub returning `[]`; `_on_stall` stub only logs |
| C-7 | `disaster_recovery.py` | `RESTResynchronizationManager.resync_all` hardcodes markets/timeframes; never wired |
| C-8 | `disaster_recovery.py` | `TelegramRetryManager` processes one message then tight-loops on failure, blocking queue |
| C-9 | `disaster_recovery.py` | `IdempotentEventProcessor.mark_processed` evicts arbitrary items from set instead of FIFO |
| C-10 | `disaster_recovery.py` | `create_backup()` calls `_verify_backup()` twice (double decompression) |
| C-11 | `observability.py:38–50` | `JsonLogFormatter` silently drops any `extra` key not in its hardcoded whitelist |

---

## 3. Database (`database/`)

### 3.1 What Works Well
- SQLite WAL + FULL synchronous + 30s `busy_timeout` + startup `PRAGMA quick_check`.
- Additive schema migrations via `_migrate_paper_trading_columns` with SQL-injection-safe `identifier_preparer.quote()`.
- Fail-closed `promote_models` / `_has_complete_promotion_evidence`: Requires purged-timestamp walk-forward OOF evidence, economic evidence, and champion evidence.
- Atomic `save_trade_history` and `save_partial_trade` transactions.

### 3.2 Bugs & Issues

| ID | Location | Issue |
|---|---|---|
| DB-1 | `repositories.py:73–88` | First `save_candles(self, candles: list[dict])` is completely shadowed by second `save_candles(self, symbol, market, timeframe, candles)` — dead code |
| DB-2 | `repositories.py:801–813` | `save_system_event` uses `session.add()` → `IntegrityError` on duplicate `event_id` |
| DB-3 | `repositories.py:584–587` | N+1 queries: 2 extra queries per row for favorite counts in `list_public_strategies` |
| DB-4 | `repositories.py:49–63, 160–186` | Row-by-row `session.get()` upserts instead of SQLite `ON CONFLICT DO UPDATE` |
| DB-5 | `models.py` | Missing indexes on: `PaperPositionModel(status, market)`, `PaperOrderModel(status, market)`, `TradeHistoryModel(position_id, closed_at)`, `SignalModel(created_at)`, `PredictionModel(is_correct, created_at)` |
| DB-6 | `connection.py:24–26` | Lazy engine init has no locking — race condition under concurrent first-access |

---

## 4. Exchange & Market Data (`exchange/`, `market/`)

### 4.1 What Works Well
- `BasePublicClient`: Proper `CancelledError` re-raising, `Retry-After` handling, bounded retries (3), clock sync.
- `WebSocketManager`: Exponential backoff (1s–30s), `ping_interval=20`, `_lifecycle_lock`.
- `Scanner._analyze_market()`: Bounded batch rotation, Semaphore concurrency, per-symbol retry backoff.
- `market/data_reliability.py`, `market/analytics.py`, `market/regime_radar.py`: Deterministic validation with explicit `INSUFFICIENT_DATA`/`INVALID_DATA` — no silent NaN/zero fallbacks.

### 4.2 Bugs & Issues

**🔴 BUG — `DataIntegrityGuardian.is_symbol_valid()` permanently blacklists symbols**  
`market/data_integrity.py:98`: Once `status["healthy"]` becomes `False`, `is_symbol_valid()` short-circuits without re-evaluating freshness or continuity. `reset_status()` is never called anywhere. Symbols that recover never re-enter scanning.  
**Fix:** Always re-run `validate_freshness` and `check_continuity`; clear failure flags on a full pass.

**🔴 BUG — `RegimeDetector` SMA-200 bug for 100–199 candles**  
`market/regime_detector.py:13–29`: Requires `len(closes) >= 100`, then calls `sma(closes, 200)`. When `100 <= len < 200`, `sma()` returns `closes[-1]` (current price). This makes `price > sma50 > sma200` always evaluate against the current price, returning wrong regimes.  
**Fix:** Guard `if len(closes) >= 200` before computing `sma200`.

| ID | Location | Issue |
|---|---|---|
| E-1 | `websocket_manager.py:162–183` | `start()` with any change to either market's stream list calls `_stop_unlocked()` and restarts BOTH Spot and Futures WebSockets |
| E-2 | `websocket_manager.py:81–85` | Handlers awaited inline inside `ws.recv()` loop — slow handler stalls all WebSocket reads |
| E-3 | `market_discovery.py:32–46` | `_fetch()` creates a new `ClientSession` per call and has zero retries on `exchangeInfo` |
| E-4 | `market_discovery.py:70,80,116,126` | `MIN_NOTIONAL` filter: Binance Spot uses `NOTIONAL` key; Futures uses `"notional"` — both silently fall back to `10.0` |
| E-5 | `rate_limiter.py:24–29` | `acquire()` spins in fixed 50ms sleep instead of sleeping the exact deficit; doesn't adapt to Binance `X-MBX-USED-WEIGHT-1M` headers |
| E-6 | `scanner.py:421–422` | `start()` registers `_stream_handler` but `stop()` never removes it → duplicate handlers on restart |
| E-7 | `momentum_analyzer.py:64–70` | `ema()` uses `np.exp(np.linspace(-1,0,period))` weights instead of standard `alpha = 2/(period+1)` recursive EMA |
| E-8 | `momentum_analyzer.py:13–28` | `rsi()` uses SMA of gains/losses instead of Wilder smoothing |
| E-9 | `volatility_analyzer.py:9–21` | `atr()` uses SMA of True Range instead of Wilder smoothing |

---

## 5. Intelligence & Strategies (`intelligence/`, `strategies/`)

### 5.1 What Works Well
- `IntelligenceCore.analyze_symbol`: Respects `DataIntegrityGuardian` and emits structured observability events.
- `IntelligenceCore.process_signals`: Deduplicates by `(symbol, market, strategy, direction)` within a 5-minute TTL.
- `ConfidenceEngine` and `DecisionEngine` structure is sound.

### 5.2 Bugs & Issues

**🔴 BUG — All strategy signals fail backtester confidence threshold**  
`strategies/base_strategy.py:27–40`: `_make_signal` sets `"raw_score"`, not `"confidence"`. `HistoricalBacktester._generate_signal` checks `signal.get("confidence", 0) >= config.min_confidence (0.6)`. **This means zero trades are ever generated in any backtest.**  
**Fix:** Add `"confidence": self._make_signal(...).get("raw_score", 0) / 100.0` or unify the key name.

| ID | Location | Issue |
|---|---|---|
| I-1 | `confidence_engine.py:L20` | `signal.get("take_profit", [0])[0]` → `IndexError` if `take_profit` is `[]` or `None` |
| I-2 | `confidence_engine.py:L12–26` | `market_regime` weight (0.2) declared but never used; hardcoded `+0.1` base instead |
| I-3 | `signal_validator.py:21–27` | Any direction other than LONG/BUY/SHORT/SELL silently passes; no `math.isfinite` on prices |
| I-4 | `decision_engine.py:25–27` | Signals failing `SignalValidator` are silently dropped — no `SIGNAL_REJECTED` event published |
| I-5 | `intelligence_core.py:96` | `trend_analyzer.get_trend_summary` called inside per-strategy loop instead of once per symbol |
| I-6 | `strategy_selector.py:32–37` | `update_performance()` raises `KeyError` on unknown strategy names; never called anywhere |
| I-7 | `strategies/all_strategies.py` | `TrendFollowingStrategy` hardcodes `"1h"`; others hardcode `"15m"` — blocks parameterized Strategy Lab |
| I-8 | `feature_engine.py:L26,L47` | Allows `len(closes) >= 20` but then calls `sma(closes, 50)` — crashes when `20 <= len < 50` |

---

## 6. Paper Trading & Risk (`paper_trading/`, `risk/`)

### 6.1 What Works Well
- `Simulator._execute_signal_locked` and `_close_position`: Strong idempotency via `order_id`, `"CLOSING"` claim lock, collateral reservation, DB-failure rollback.
- `FundingCalculator`: Accurate notional-based funding on UTC 8h boundaries.
- `RiskManager`: Clean finite-value validation and asset-exposure grouping.

### 6.2 Bugs & Issues

**🔴 BUG — Partial close audit uses remaining amount instead of closed quantity**  
`paper_trading/simulator.py:780–829`: `_partial_close_position` mutates `position["amount"] = amount_before - quantity` at L780, then computes `gross_independent = ... * float(position["amount"])` at L814 (using the *remaining* amount). This triggers false `DISCREPANCY` errors and sets `risk_calculation_verified = False` on every partial close.  
**Fix:** Use `quantity` (not `position["amount"]`) in the gross P&L cross-check at L814.

**🔴 BUG — `AdaptiveRiskEngine` is completely disconnected**  
`risk/adaptive_risk.py` is never instantiated or called in `Orchestrator`, `Simulator`, or `RiskManager`. The `RiskAction.CLOSE_RISKIEST_POSITIONS` case is an explicit stub (`"requires simulator integration"`).  
**Status:** The 10-factor adaptive risk system is built but has zero runtime effect.

**🔴 BUG — Cooldown permanently pauses new position entries**  
`risk/adaptive_risk.py:872–876`: `_apply_actions` sets both `_cooldown_until` and `_paused = True`. `is_paused()` and `can_open_position()` check `self._paused` without clearing it when `datetime.now(timezone.utc) >= _cooldown_until`. Once triggered, the engine stays permanently paused until manual `reset_cooldown()`.

| ID | Location | Issue |
|---|---|---|
| PT-1 | `simulator.py` | `update_prices()`, `cancel_limit_order()`, `check_limit_orders()` don't acquire `_account_lock` — concurrent mutation possible |
| PT-2 | `liquidation_engine.py:25,46,66` | Checks `position["side"] == "LONG"` — `"BUY"` direction treated as SHORT |
| PT-3 | `fee_calculator.py:20–26` | Always charges taker fee regardless of LIMIT vs MARKET order type |
| PT-4 | `simulator.py` | `_calculate_order_quantity` sizes against `balance` while `_execute_signal_locked` caps against `equity` — inconsistent base |
| R-1 | `adaptive_risk.py` | Effective limits reduced by `_apply_actions` but never restored when risk returns to NORMAL |
| R-2 | `adaptive_risk.py:70` | `funding_warning_pct = 0.05` means 0.05% but `_calculate_funding_risk` returns percentage points (100x mismatch) |

---

## 7. ML / Learning Pipeline (`learning/`)

### 7.1 What Works Well
- `confidence_gate.py` (`ModelPromotionGate`): Rigorous fail-closed OOF classification, calibration, drawdown, stability, net-expectancy gating.
- `strategy_comparison.py`, `strategy_dna.py`, `regime_performance.py`, `trade_review.py`, `model_lifecycle.py`: Clean, leakage-aware, honest reporting.

### 7.2 Critical Pipeline Bugs

**🔴 BUG — Walk-forward validator doesn't validate the actual deployed pipeline (scaler mismatch)**  
`learning/walkforward_validator.py:247–269`: Fits RF & XGBoost on **unscaled** `X_train`.  
`learning/trainer.py:156–166`: Fits `StandardScaler` on `X` and trains on `Xs` (scaled).  
`learning/predictor.py:69`: Scales input with `self.scaler` at inference time.  
**Result:** Walk-forward OOF metrics measure performance of an unscaled model that is never actually deployed. Reported accuracy is not predictive of live performance.  
**Fix:** Wrap RF/XGBoost in `sklearn.pipeline.Pipeline([("scaler", StandardScaler()), ("model", ...)])` inside `WalkForwardValidator`.

**🔴 BUG — Live ML retraining always blocked by regime="UNKNOWN"**  
`learning/live_service.py:577`: `_record_prediction` hardcodes `"regime": "UNKNOWN"`.  
`learning/confidence_gate.py:270–271`: `_economic_evidence` rejects any dataset with `regime in {"", "UNKNOWN", "NONE"}`.  
**Result:** Every live retraining attempt is blocked by its own data. The ML pipeline never actually retrains on live predictions.  
**Fix:** Populate regime from `TrendAnalyzer` or regime detection logic in `_record_prediction`.

**🔴 BUG — `_validate_active_champions` refits and overwrites champion weights**  
`learning/trainer.py:132–142`: Loads the saved champion, then passes it to `validator.validate()`, which calls `model.fit(X_train, y_train)` on the unscaled data — **refitting and overwriting the champion** every validation cycle.

**🔴 BUG — `HistoricalBacktester._check_exit` reads live candles (look-ahead bias)**  
`learning/backtest_engine.py:422`: `_check_exit` calls `self.candles.get_series(..., "1m", limit=1)` which always reads the **latest live candle** instead of historical data at `current_time`. Every backtest has severe look-ahead bias.

| ID | Location | Issue |
|---|---|---|
| ML-1 | `backtest_engine.py:273,282` | Trades appended on open AND close → every closed trade is duplicated in results |
| ML-2 | `backtest_engine.py:470` | `trade.slippage += abs(exit_slippage - exit_price) * amount` — subtracts price from a small delta, inflating slippage to ~100% of notional |
| ML-3 | `model_manager.py:184–195` | `evaluate_challenger` uses `joblib.load()` which crashes on XGBoost `.json` files |
| ML-4 | `model_manager.py:298–299` | `promote_challenger` requires `champions["rf"]["status"] == "ok"` — impossible for initial champion promotion |
| ML-5 | `model_manager.py:325–333` | Mutates detached champion object in a different session — old champion never demoted in DB |
| ML-6 | `strategy_lab.py:207` | Typo `_signed_signed_signed_number` → `NameError` on any Futures run with `funding_rate` set |
| ML-7 | `strategy_lab.py:251` | Division by `abs(entry_fill - stop_loss)` can be `ZeroDivisionError` on gap opens |
| ML-8 | `strategy_evolution.py:273,288` | `run_backtest` computes `test_params` but never passes them to `BacktestConfig` or strategies |
| ML-9 | `strategy_evolution.py:548–568` | `_get_shadow_performance` and `_get_baseline_shadow_performance` return **hardcoded dummy metrics** |
| ML-10 | `strategy_evolution.py:469,543` | `_evaluate_backtest_criteria` reads `"sharpe"` but `_compare_results` writes `"test_sharpe"` — always rejects |
| ML-11 | `performance_analyzer.py:132–179` | `_identify_failure_patterns` passes already-filtered `failures` to `_group_by()` — `accuracy` is always `0.0` |
| ML-12 | `live_service.py:595–623` | Online River updates computed but never applied to `self.predictor.river_model` — online learning has no effect |
| ML-13 | `live_service.py:157,564` | Only passes `{"1h": ...}` to `FeatureEngine`, leaving 27/36 features at `0.0` during both training and inference |

---

## 8. Monitoring (`monitoring/`)

### 8.1 Status: Built but Completely Disconnected
`monitoring/drift_monitor.py` defines `DriftMonitor` with 7 drift detection metrics (accuracy, Brier calibration, strategy Sharpe, feature PSI, regime stability, data quality, system resources). The entire module is **never instantiated or called** in `core/orchestrator.py` or anywhere at runtime.

| ID | Issue |
|---|---|
| MON-1 | Never instantiated — zero runtime effect |
| MON-2 | `_regime_stability_days` increments per `check_all()` call, not per elapsed day |
| MON-3 | `_check_system_resources` returns on first CPU warning, never checks memory or disk |
| MON-4 | `MIN_VALIDATION_ACCURACY`, `Repository`, `AdaptiveRiskEngine` imported but never used |

---

## 9. Tauri Desktop Shell (`blackmarket-desktop/src-tauri/`)

### 9.1 What Works Well
- Single-instance enforcement via `tauri_plugin_single_instance`.
- API token generated once per installation (`api-token` file, 32-char hex UUID, `create_new(true)`).
- Shutdown token is ephemeral per-launch, never exposed to frontend.
- `backend_api_token()` refuses to return until backend is `"ready"`.
- Backend log rotation: 10 MB limit, 3 backups, with sensitive-entry redaction.
- Strict production CSP (`script-src 'self'`, `object-src 'none'`, no eval).
- Graceful shutdown: `POST /_internal/shutdown` → 30s wait → `child.kill()`.
- Rust tests: All 6 pass (health probe, log-tail bounds, redaction).

### 9.2 Issues

| ID | Location | Issue |
|---|---|---|
| T-1 | `backend.rs:471–500` | `api-token` persists across launches — if file is corrupted, startup fails permanently until manually deleted |
| T-2 | `tauri.conf.json:33–52` | `bundle.resources` packages BOTH raw `.py` source tree AND PyInstaller `BlackMarketBackend.exe` — double-bundles the backend |
| T-3 | `START_BLACKMARKET.bat:30` | Missing `--config src-tauri/tauri.dev.conf.json` — production CSP blocks Vite HMR WebSocket in dev mode |

---

## 10. React/TypeScript Frontend (`blackmarket-desktop/src/`)

### 10.1 What Works Well
- 16 implemented screens (no pure stubs): Overview, Markets, AI Signals, Market Analysis, Portfolio, Positions, Trade History, Intelligence, Learning, Autonomous, Strategy Lab, Community Library, Risk Management, Activity, Diagnostics, Settings.
- `backendClient.ts`: AbortController 10s timeouts, 2 retries on transient errors, 60s rolling request metrics, diagnostic event recording.
- `frontendDiagnostics.ts`: Bounded 500-event buffer, URL/token redaction, 50-event batch upload every 5s.
- `marketData.ts`: Proper snapshot freshness enforcement (<= 120s), candle deduplication, merge sort-order guarantee.
- 23/23 service tests pass, 0 lint warnings/errors, build passes.

### 10.2 Bugs

**🔴 BUG — WebSocket `subscribe()` callbacks never fire in Tauri desktop**  
`services/websocket.ts:315–334`: In SSE mode, `source.onmessage` calls `this.subscriptions.get(channel)?.forEach(callback)`. In WebSocket mode, `handleMessage` only calls `this.emit(channel, event)` (which reads `this.listeners`, not `this.subscriptions`).  
`App.tsx:643–646` uses `socket.subscribe(channel, ...)`, so **all real-time WebSocket push updates never trigger UI refreshes in the Tauri desktop app**. The app silently falls back to 10s/30s polling.  
**Fix:** In `handleMessage()`, also call `this.subscriptions.get(message.channel)?.forEach((cb) => cb(message.event))`.

| ID | Location | Issue |
|---|---|---|
| UI-1 | `App.tsx:1327` | Direct DOM `parentElement?.remove()` on React-managed toast node — `NotFoundError` during reconciliation |
| UI-2 | `App.tsx:153` vs `DashboardScreens.tsx:419` | App fetches 12 timeframes; `AnalysisScreen` renders only 9 and hardcodes `<SummaryCard value="9" />` |
| UI-3 | `App.tsx:1198` | `\\n\\n` literal instead of `\n\n` in assistant fallback text |
| UI-4 | `App.tsx:493` | Redundant ternary — both branches produce identical URL |
| UI-5 | `DashboardScreens.tsx:1336` | `max_spot_positions` / `max_futures_positions` inputs use `min="0.01" step="any"` — should be `step="1" min="1"` |

### 10.3 Dead Code & Unused Dependencies

The following files exist in the repo but are **never imported** by `App.tsx` or `DashboardScreens.tsx`:

| Dead File | Used By |
|---|---|
| `stores/marketStore.ts` | Nobody |
| `components/charts/MarketChart.tsx` | Nobody — also **broken** (uses removed v4 API: `addCandlestickSeries()`) |
| `components/panels/Overview.tsx`, `HeatmapPanel.tsx`, `LongShortPanel.tsx`, `MarketBreadthPanel.tsx`, `PortfolioPanel.tsx`, `RiskPanel.tsx`, `VolumePanel.tsx` | Nobody |
| `services/api.ts` (`ApiService` via axios) | Only the dead panel files above |

**Unused `package.json` dependencies:**  
- `@tanstack/react-query` — never imported anywhere  
- `axios` — only used by dead panel files  
- `zustand` — only used by dead `marketStore.ts`

**Duplicate service files:**  
- `services/localAuth.ts` / `localAuth.js` / `localAuth.d.ts` — same 13-line implementation tripled  
- `services/backendClient.ts` + `backendClient.js` (`.js` is a re-export shim for the test runner)

---

## 11. Terminal Dashboard (`terminal/dashboard.py`)

> [!WARNING]
> The terminal dashboard is largely non-functional due to wrong attribute names and incorrect Textual API usage.

| ID | Issue |
|---|---|
| TUI-1 | Reads `self.orchestrator._repo` — attribute is `self.orchestrator.repo` — Strategy/Learning tabs always broken |
| TUI-2 | Reads `orchestrator._scanning`, `_ws_connected`, `_tracked_symbols`, `_recent_snapshots` — all never updated, `_symbol_tiers` doesn't exist |
| TUI-3 | `TabPane` yielded directly inside `Tabs(...)` — Textual requires `TabbedContent` for `TabPane` |
| TUI-4 | `HealthMonitor` schema mismatch — reads `"status"/"message"` but monitor stores `"healthy"/"details"` |
| TUI-5 | Hardcodes `$500`/`$1,000` initial balances; ignores `simulator.initial_spot_balance` |
| TUI-6 | `def log()` shadows Textual's built-in `App.log` property |
| TUI-7 | `await self.quit()` — Textual uses `self.exit()` |
| TUI-8 | Instantiates `LiquidationEngine()` inside the render loop every 2 seconds |
| TUI-9 | `UnboundLocalError` on `regime` if `selector.weights` is empty |

---

## 12. Build & CI

| ID | Location | Issue |
|---|---|---|
| CI-1 | `START_BLACKMARKET.bat:30` | Missing `--config src-tauri/tauri.dev.conf.json` — production CSP blocks Vite HMR |
| CI-2 | `tauri.conf.json:33–52` | `bundle.resources` ships both raw `.py` source AND `BlackMarketBackend.exe` (double-bundled) |
| CI-3 | `build_release.ps1:21–27` | Doesn't exclude `resources/backend/` (PyInstaller) or `blackmarket-web/.next/` from release archive |
| CI-4 | `scripts/verify_release_version.py:25` | Still reads `blackmarket-web/package.json` version — should be removed if `blackmarket-web` is retired |
| CI-5 | Starlette deprecation warning | `starlette.testclient` recommends `httpx2` instead of `httpx` — resolve before `httpx` deprecation becomes a break |
| CI-6 | Python 3.12 | Local tests run on 3.13 only; `pyproject.toml` requires `>=3.12` but Python 3.12 CI is not verified |
| CI-7 | Uncommitted working tree | `release-manifest.json` records `sourceCommit: local-uncommitted` and `signatureStatus: NotSigned` — cannot be published as a release |

---

## 13. Release Blockers

These items **must** be resolved before any public release:

1. 🔴 **Telegram token** — Previously present in `.env.example`, found in commit `0415b531e14efa7e03c932a6c1e7ee8492105179`. Revoke via BotFather. Scan all published history and release artifacts.
2. 🔴 **Uncommitted working tree** — Establish a reviewed source commit; run CI against it.
3. 🔴 **Installer unsigned** — `signatureStatus: NotSigned`. Obtain a code-signing certificate or clearly disclose the status.
4. 🔴 **No clean-machine installer acceptance** — The installer has never been validated on a clean Windows machine with Python removed from `PATH`.
5. 🔴 **Sensitive data in git history** — SQLite DBs, backup archives, and `.next/` build output are tracked. Remove safely before publication.
6. 🔴 **Legacy Next.js source** — `blackmarket-web/` has no account-level authorization. Must be excluded from any hosted deployment or removed from the repo before public access.

---

## 14. Prioritized Upgrade Roadmap

### 🔴 P0 — Fix Now (Runtime Correctness)

| # | Action | File(s) |
|---|---|---|
| 1 | Import `create_default_registry` in `assistant.py` | `src_tauri/backend/api/routes/assistant.py` |
| 2 | Fix analytics evidence key map in `intelligence.py:105–109` | `api/routes/intelligence.py` |
| 3 | Replace `float('inf')` profit_factor with `None` | `bridge/orchestrator_bridge.py:592` |
| 4 | Add `.isascii()` guard in `shutdown_backend` | `main.py:497` |
| 5 | Wrap `EventBus._persist` in try/except | `core/event_bus.py:80–81` |
| 6 | Offload Telegram awaits to background queue | `core/orchestrator.py:593–977` |
| 7 | Fix partial-close audit math (use `quantity` not remaining amount) | `paper_trading/simulator.py:814` |
| 8 | Acquire `_account_lock` in `update_prices`, `check_limit_orders`, `cancel_limit_order` | `paper_trading/simulator.py` |
| 9 | Fix LiquidationEngine side check (`"BUY"` → LONG branch) | `paper_trading/liquidation_engine.py:25,46,66` |
| 10 | Fix WebSocket `subscribe()` callback dispatch in `handleMessage()` | `services/websocket.ts:320–322` |
| 11 | Fix `save_candles` shadow / `save_system_event` upsert | `database/repositories.py` |

### 🟠 P1 — Fix Soon (ML Pipeline Integrity)

| # | Action |
|---|---|
| 12 | Align scaler: wrap RF/XGBoost in `Pipeline([("scaler", StandardScaler()), ...])` inside `WalkForwardValidator` |
| 13 | Populate real `regime` in `LiveLearningService._record_prediction` |
| 14 | Fix `_validate_active_champions` — evaluate frozen artifacts instead of refitting |
| 15 | Fix `HistoricalBacktester`: use `raw_score/100.0` for confidence; fix look-ahead in `_check_exit`; remove trade deduplication |
| 16 | Fix `StrategyLab` `NameError` and `ZeroDivisionError`; pass `config.timeframe` |
| 17 | Fix `PerformanceAnalyzer._identify_failure_patterns` — compute accuracy on all preds, not failures |
| 18 | Wire `AdaptiveRiskEngine` into `Orchestrator`/`Simulator` or mark experimental |
| 19 | Apply River online-learning updates to `predictor.river_model` |

### 🟡 P2 — Improve (Quality & Completeness)

| # | Action |
|---|---|
| 20 | Unify `TIMEFRAMES` across all backend modules into one shared constant |
| 21 | Add `ge=1` to all `limit` query params |
| 22 | Add Pydantic schemas with `extra="forbid"` for `strategy-lab` and `weaknesses` endpoints |
| 23 | Fix `DataIntegrityGuardian` — always re-evaluate on `is_symbol_valid()` for self-healing |
| 24 | Fix `RegimeDetector` SMA-200 guard for `len(closes) < 200` |
| 25 | Standardize `ema()`, `rsi()`, `atr()` to standard recursive/Wilder formulas |
| 26 | Fix WebSocket `start()` to manage Spot/Futures tasks independently |
| 27 | Dispatch WS handlers via `create_task` to keep `ws.recv()` responsive |
| 28 | Add missing indexes on 5 high-churn DB tables |
| 29 | Batch-upsert candles/symbols with `ON CONFLICT DO UPDATE` |
| 30 | Wire `DriftMonitor` into `Orchestrator.refresh_health_status()` |
| 31 | Fix `AdaptiveRiskEngine` cooldown — clear `_paused` when cooldown expires; add limit recovery at NORMAL |
| 32 | Fix `START_BLACKMARKET.bat` — add `--config src-tauri/tauri.dev.conf.json` |
| 33 | Fix `build_release.ps1` — exclude `resources/backend/` and `.next/` from archive |

### 🔵 P3 — Cleanup & Polish

| # | Action |
|---|---|
| 34 | Delete dead files: `MarketChart.tsx`, `stores/marketStore.ts`, `components/panels/*`, `services/api.ts` |
| 35 | Remove unused `package.json` deps: `@tanstack/react-query`, `axios`, `zustand` |
| 36 | Consolidate `localAuth.ts`/`.js`/`.d.ts` to single implementation |
| 37 | Delete unused `src_tauri/backend/api/schemas.py` |
| 38 | Repair terminal dashboard: attribute names, Textual API (`TabbedContent`, `self.exit()`), dynamic balances |
| 39 | Fix `TelegramClient` HTML escaping and `signal.get("reason")` key |
| 40 | Escape HTML in all Telegram `parse_mode="HTML"` messages |
| 41 | Add chunk code-splitting to bring main JS bundle below 500 KB |
| 42 | Resolve Starlette/httpx `TestClient` deprecation warning |

---

## Overall Scoring

| Area | Score | Key Evidence |
|---|:---:|---|
| Test suite coverage | 🟢 8/10 | 684 Python + 23 desktop + 6 Rust tests all pass |
| Backend auth & security | 🟢 7.5/10 | Fail-closed auth, loopback enforcement, CSP, secret redaction |
| Paper trading simulation | 🟡 6.5/10 | Partial-close math bug; 3 missing account locks; fee model gaps |
| Market data & exchange | 🟡 6/10 | Permanent symbol blacklist bug; non-standard indicator math; WS restart drops both markets |
| ML / learning pipeline | 🔴 3.5/10 | Live retraining permanently blocked; scaler mismatch; backtester generates 0 trades; look-ahead bias |
| Risk engine | 🔴 2/10 | AdaptiveRiskEngine built but never wired; cooldown permanently pauses |
| Monitoring | 🔴 2/10 | DriftMonitor built but never instantiated |
| Desktop frontend | 🟡 7/10 | WS push callbacks broken; dead legacy code; build/tests all pass |
| Tauri shell | 🟢 7.5/10 | Solid supervision; minor token/bundling issues |
| Terminal dashboard | 🔴 3/10 | Wrong attribute names; wrong Textual API; hardcoded values |
| **Overall** | 🟡 **5.5/10** | **Functional beta for paper trading; several subsystems non-operational** |

---

*Report generated by full automated + subagent deep-code audit on 26 November 2026. All file paths and line numbers verified against the working tree at commit `466dbc7` with uncommitted changes.*
