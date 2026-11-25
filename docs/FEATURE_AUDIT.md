# Feature and Implementation Audit

Review date: 25 November 2026  
Supported product: Tauri desktop + local Python backend  
Trading mode: paper simulation only

This audit maps the first-party product surfaces to their implementation boundaries and current evidence. “Implemented” means source and wiring exist; it does not mean every service is active in every configuration. “Verified” requires a named test or runtime acceptance check. The generated [symbol catalog](SYMBOL_CATALOG.md) lists source-level function candidates, not proof of correct behavior.

## Runtime Status Definitions

- **Implemented:** first-party code and a user-facing or API path exist.
- **Partial:** some path exists, but an identified dependency, workflow, or acceptance step is incomplete.
- **Unverified:** code exists, but this workspace has not demonstrated the live or packaged behavior.
- **Not supported:** intentionally excluded from the product contract.

The Diagnostics screen reports current backend/API/database/WebSocket/scanner/learning/paper-trading status, recent persisted events, a bounded local process-log tail, and rolling frontend HTTP request counts and latency. It does not introspect every Python function or guarantee every feature is operational. Unknown state is shown as unknown, not healthy.

## Desktop Screens

| Screen | Main implementation | Backend/data boundary | Status and evidence |
| --- | --- | --- | --- |
| Overview | `blackmarket-desktop/src/App.tsx`, `src/components/panels/` | Market snapshot, candles, portfolio, risk, learning and activity requests | Implemented; desktop build passes. Live market freshness depends on Binance/network state. |
| Markets | `src/screens/DashboardScreens.tsx` | Market discovery, symbol eligibility, scanner and market list routes | Implemented; live exchange availability unverified. |
| AI Signals | `src/screens/DashboardScreens.tsx` | Signal list, strategy, market, reason and freshness data | Implemented; quality/profitability is not established. |
| Market Analysis | `src/screens/DashboardScreens.tsx` | Candle-history requests for configured chart intervals and analysis routes | Implemented; currently requests multiple intervals on screen refresh. Performance is instrumented but not yet baselined under representative live use. |
| Portfolio | `src/screens/DashboardScreens.tsx` | Simulated balances, positions, trades and statistics | Implemented; paper account only. |
| Positions | `src/screens/DashboardScreens.tsx` | Simulated positions, orders, close/update/cancel/manual paper actions | Implemented; tests cover API behavior, not every manual Tauri interaction. |
| Trade History | `src/screens/DashboardScreens.tsx` | Persisted simulated trades and summary statistics | Implemented; database persistence paths have backend regression coverage. |
| Intelligence | `src/screens/DashboardScreens.tsx` | Intelligence summary, strategy weights, regime and market analysis | Implemented; underlying data may be unavailable or insufficient. |
| Learning | `src/screens/DashboardScreens.tsx` | Prediction outcomes, model registry, validation and performance APIs | Implemented; no fresh training or performance claim is made by this audit. |
| Autonomous | `src/screens/DashboardScreens.tsx` | Readiness, decisions, paper-entry controls and optional Telegram test | Implemented; real-money execution is not supported. External Telegram delivery is configuration/service dependent. |
| Strategy Lab | `src/screens/DashboardScreens.tsx` | Backtests, comparison, saved strategies, reports and workspaces | Implemented; backtest outputs are research evidence, not future performance. |
| Community Library | `src/screens/DashboardScreens.tsx` | Local pseudonymous publishing, versions, favorites and reports | Implemented locally; hosted synchronization and independent performance verification are not supported. |
| Risk Management | `src/screens/DashboardScreens.tsx` | Risk limits, exposure and persisted risk events | Implemented; adaptive factors can remain unavailable if validated evidence is absent. |
| Activity | `src/screens/DashboardScreens.tsx` | Persisted application event history | Implemented; this is event history, not raw process logging. |
| Diagnostics | `src/screens/DashboardScreens.tsx`, `src-tauri/src/backend.rs` | Health endpoint, authenticated event history, supervisor status, bounded process-log tail | Implemented in this change; frontend and Rust checks pass. Full interactive Tauri acceptance remains pending. |
| Settings | `src/screens/DashboardScreens.tsx` | Runtime settings and assistant-intelligence configuration | Implemented; API validates accepted settings. |

## Backend Feature Areas

| Area | Implementation | Current status |
| --- | --- | --- |
| Application lifecycle and observability | `core/orchestrator.py`, `core/observability.py`, `core/event_bus.py`, `core/health_monitor.py`, `src_tauri/backend/main.py` | Implemented. Event-bus overflow is best-effort and can drop queued events; watchdog stall detection does not automatically restart components. |
| Exchange access | `exchange/spot_client.py`, `exchange/futures_client.py`, `exchange/market_discovery.py`, `exchange/websocket_manager.py` | Public Binance market-data paths implemented. Production stream availability and recovery are unverified. No private order/signing path is supported. |
| Market analysis | `market/`, `intelligence/` | Scanner, candles, features, regimes, freshness checks and signal validation implemented; outputs depend on input quality and service state. |
| Strategies and research | `strategies/`, `learning/strategy_lab.py`, `src_tauri/backend/api/routes/research.py` | Strategy families, backtests, comparisons, reports and workspaces implemented; no profitability guarantee. |
| Paper execution and risk | `paper_trading/`, `risk/`, API routes for positions/trades/risk | Simulated order lifecycle and risk controls implemented. Adaptive drawdown/correlation can be unavailable when evidence is not supplied. |
| Learning/model lifecycle | `learning/`, API routes for learning | Outcome storage, training/evaluation, model registry and promotion checks implemented; fresh model training was not run for this change. |
| Assistant | `src_tauri/backend/assistant_*.py`, assistant API routes | Local-data assistant, tools/tasks, feedback/preferences and memory paths implemented; optional external provider behavior depends on configuration. |
| Persistence/recovery | `database/`, `core/disaster_recovery.py`, backup API routes | SQLite persistence, integrity and recovery code implemented. Restore acceptance remains unverified; application-level encryption is not provided. |
| Notifications | `notifications/`, Telegram API routes | Optional Telegram integration implemented, disabled by default; live delivery is unverified. |
| Terminal UI | `terminal/` | Textual interface implemented; this implementation pass did not perform terminal UI acceptance. |

The FastAPI route surface is registered from `src_tauri/backend/api/routes/` and includes health/system, markets, signals, portfolio, positions, trades, risk, learning, intelligence, autonomous controls, settings, activity, assistant, research, community, share challenges, evolution, Telegram and backup operations. The exact route and function definitions are in source and the generated symbol catalog; route existence is not a substitute for authorization and behavior tests.

## Connectivity and Performance

- Desktop REST uses the loopback API with bearer authentication; browser development uses the local Vite proxy. Authenticated WebSocket is used by Tauri; the browser preview uses the same-origin event stream proxy.
- The Diagnostics screen refreshes health every 10 seconds and the process-log tail every 2 seconds only while that screen is open. Persisted activity reuses the app's shared 30-second refresh. The log reader is bounded to 64 KiB, 200 lines, and 2,000 characters per line; common sensitive entries are redacted.
- Backend HTTP metrics are rolling 60-second counts, failed request count, average duration and p95 duration. They contain no request path or query values. The metrics include retry attempts as part of the one logical client request and exclude native Tauri log-tail reads.
- Existing dashboard polling is unchanged. Before changing its intervals, compare Diagnostics metrics and interaction responsiveness under representative market symbols and screens. No before/after live-market performance benchmark was available in this implementation pass.

## Intentionally Unsupported or Not Yet Verified

- **Real-money exchange trading:** not supported; no exchange private order execution is included.
- **Production Next.js hosted app:** not supported; the retained Next.js tree is legacy/reference source.
- **Live exchange certification:** unverified; offline tests do not establish production network/stream recovery.
- **Signed public installer:** blocked in this environment. No valid code-signing certificate or `signtool.exe` was found in the standard Windows certificate stores/tool lookup. The existing installer is unsigned.
- **Current-source installer acceptance:** installer build and checksum are verified; clean-machine install/readiness/shutdown/uninstall smoke test is pending.
- **Complete visual/keyboard acceptance:** pending manual desktop interaction checks.
- **Backup restore and fresh model performance:** not verified by this implementation pass.

## Verification Performed During This Implementation

- Backend: `python -m pytest -q -m "not live"` using `.venv`: **670 passed, 3 live deselected**; one existing Starlette/httpx deprecation warning.
- Desktop services: `npm test`: **17 passed**.
- TypeScript/Vite: production build passed after Diagnostics and metrics integration; the existing main-chunk warning remains (latest build approximately 567 kB).
- Rust: `cargo test --manifest-path blackmarket-desktop/src-tauri/Cargo.toml --lib`: **5 passed**, including the final redaction marker checks.
- Desktop lint: `npm run lint` completed with no reported issues after the final UI changes.
- Windows installer: current-source 1.0.0 artifact is 63,416,271 bytes; SHA-256 `058d20af3191d98a8b8edecdce2e9cf272a51e76cc119924ede1fa99ed1f7db1`; manifest checksum matches; Authenticode `NotSigned`; clean-machine acceptance was not run.