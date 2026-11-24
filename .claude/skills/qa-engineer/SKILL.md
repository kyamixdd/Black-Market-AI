---
name: qa-engineer
description: Automated tests, integration testing, regression testing, and acceptance criteria.
---

# QA Engineer

Protect correctness and prevent regressions.

## Required tests
- Binance credentials absent: application starts.
- Spot discovery: eligible symbols discovered.
- Futures discovery: eligible contracts discovered.
- WebSocket interruption: automatic recovery.
- Nine timeframes: correct candle alignment.
- Duplicate signals: deduplicated.
- Paper trading: correct accounting.
- Learning: historical outcomes evaluated.
- Model update: validation required.
- Restart: balances and positions restored.
- Telegram failure: core engine continues.
- Telegram notifications are disabled by default; the backend starts without bot credentials unless the user explicitly enables Telegram.
- Real trading: impossible in this release.
- Desktop startup: backend readiness is required before dashboard data is shown.
- Desktop process management: duplicate launches do not create duplicate backends; app exit stops its managed backend.
- Startup failures: missing Python/dependencies, port conflicts, and database integrity errors produce diagnostics without fake data.
- Windows batch tools: start delegates to Tauri, stop requests graceful app exit, and check is read-only.
- Managed backend exit: valid supervisor authorization reaches Uvicorn's shutdown path; missing/invalid authorization cannot stop the backend.
- Production Windows packaging: build and launch the NSIS app, verify startup readiness, and verify graceful shutdown before claiming release readiness.
- Runtime-check dashboard heatmap and breadth against persisted snapshots when the in-memory cache is empty.
- Verify Tauri-managed recovery backups resolve under the configured per-user data directory, not the install/current working directory.
- Simulate a client closing during a WebSocket send; treat the closed-peer race as a disconnect while allowing unrelated runtime errors to surface.

## Test approach
Use pytest and pytest-asyncio. Prefer deterministic fixtures and mocked exchange responses.

Test edge cases:
- Missing candles.
- Out-of-order timestamps.
- Duplicate events.
- Network timeouts.
- Rate limits.
- Partial fills.
- Stop-loss and take-profit collisions.
- Insufficient balance.
- Daily loss limit reached.
- Database interruption.
- Model rollback.

Run relevant tests after every change. Do not claim tests passed unless they were actually executed. Report failures with reproducible steps.

## Phase 2 regression requirements
- Test unauthorized and authorized REST separately, and test WebSocket authentication before subscriptions/private payloads.
- Exercise production-orchestrator recovery and shutdown, including open positions and orders, repeated recovery without duplication, database backup integrity, and completed-trade/position-close consistency.
- Verify frontend market readiness fails closed on missing snapshots/candles and changes chart identity for symbol, market, and timeframe.
- Run the warning audit without suppressing third-party deprecations. Separate Python dependency warnings and legacy frontend lint warnings from application defects.
- Native Windows package/startup/shutdown verification remains a per-build release gate; do not infer it from frontend builds or Python tests. The 1.0.0 x64 NSIS bundle's install, readiness, loopback auth, duplicate-launch behavior, and graceful window close were exercised on this Windows host with the project Python environment. It is not self-contained; interactive button/visual checks, clean-machine installation, and forced-crash recovery remain unverified.
- Before a Tauri build, record Python, Node/npm, Rust/Cargo, MSVC/Windows SDK, and WebView2 availability. Run Tauri CLI configuration inspection first; do not attempt compilation when required toolchain components are missing. Do not replace or silently mutate the user's global Python environment.
