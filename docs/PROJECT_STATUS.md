# Project Status and Audit

Review date: 25 November 2026
Product version: `1.0.0`  
Release classification: desktop beta candidate; web production unsupported
Source identity: baseline commit `466dbc7` on `Black-Market-AI-Beta-1.0.1`; working tree has uncommitted changes.

## Assessment

**Overall score: 6.0/10 — functional beta; not ready for unrestricted public release.**

The score is an engineering-readiness assessment, not a financial-performance rating. It reflects source breadth, current local test/build evidence, safety defects, operational verification, and release provenance.

| Area | Score | Evidence |
|---|---:|---|
| Shared frontend | 7.0/10 | Production build and 8-viewport browser smoke pass; lint reports maintainability and hook warnings; complete Tauri UI acceptance remains open |
| Python backend and API | 7.5/10 | Backend regression suite passes on Python 3.13; desktop API has bearer authentication, loopback checks, restricted CORS, and authenticated WebSocket setup |
| Market data | 6.0/10 | Public Spot/Futures REST scanning and bounded dynamic ticker-stream subscriptions are implemented; live production stream availability/recovery has not been verified |
| Paper trading and risk | 6.0/10 | Simulated order lifecycle and atomic close persistence exist; adaptive drawdown/correlation are calculated only when validated evidence is supplied |
| Learning and research | 6.5/10 | Walk-forward validation, outcome records, model lifecycle and promotion gates exist; no fresh training or performance validation was run |
| Persistence and recovery | 7.0/10 | SQLite integrity checks, backup/recovery paths, and ID-based position recovery exist; database and backup confidentiality is not provided |
| Desktop packaging | 5.0/10 | Current-source NSIS artifact builds with a bundled backend; signature and clean-machine acceptance remain open |
| Automated verification | 8.0/10 | 670 Python tests, 17 desktop service tests, 5 Rust tests, dependency scans, and frontend builds pass; three live exchange tests were deselected |
| Public release readiness | 3.5/10 | No reviewed release commit, signed artifact, current-head CI, or clean-machine acceptance |

## Verification run in this workspace

- `.\.venv\Scripts\python.exe -m pytest -q -m "not live"`: 670 passed, 3 live tests deselected. Starlette emits an httpx TestClient deprecation warning.
- Backend `pip-audit -r src_tauri\backend\requirements.txt`: no known vulnerabilities; `pip check`: no broken requirements.
- Desktop npm audit reported zero vulnerabilities.
- A Python wheel built and installed into an isolated target; expected `benchmarks`, `risk`, `monitoring`, and `src_tauri.backend` imports passed from a clean working directory on Python 3.13. Python 3.12 CI verification remains pending.
- `blackmarket-desktop`: `npm test` passed 17 tests; `npm run build` passed; `npm run lint` completed without reported issues.
- Tauri supervisor: `cargo test --manifest-path blackmarket-desktop/src-tauri/Cargo.toml --lib` passed 5 tests, including bounded log-tail and redaction checks.
- Responsive browser smoke passed at 8 widths from 320 to 1920 pixels, checking horizontal overflow, primary navigation, chart-settings interaction, and page errors.
- The legacy Next.js source is not part of desktop packaging and is no longer built or deployed by supported workflows.
- The latest desktop frontend build emitted a 567.14 kB main chunk warning.
- A current-source 1.0.0 x64 NSIS installer was built locally at 63,416,271 bytes. `release-output/release-manifest.json` records SHA-256 `058d20af3191d98a8b8edecdce2e9cf272a51e76cc119924ede1fa99ed1f7db1`, `sourceCommit: local-uncommitted`, and `signatureStatus: NotSigned`. The manifest checksum matches the installer. No clean-machine install/readiness/shutdown/uninstall smoke was run because a prior installation and shared app-data directory exist; visual/custom-button interaction remains unverified.
- Production exchange streams, backup restore, and full manual UI workflows were not verified in this audit.

## Implemented product areas

- Public Binance Spot and USDⓈ-M Futures market discovery, REST data, candles, scanner, and stream-management code.
- Technical analysis, multi-timeframe signals, market breadth, volume, long/short, regime, and data-freshness checks.
- Strategy families, Strategy Lab, historical backtesting, comparison, and saved research reports.
- Paper Spot/Futures orders and positions, simulated fees/slippage/funding, leverage/liquidation handling, and persisted trade history.
- Runtime risk limits, paper-trading readiness checks, and settings validation.
- Prediction outcomes, model registry, confidence calibration, chronological validation, promotion and rollback gates.
- Market intelligence, assistant, research, strategy evolution, drift monitoring, trade review, workspaces, public strategy library, and shareable analysis.
- SQLite persistence, integrity checks, backups, restore, event persistence, and recovery routines.
- Tauri desktop with its React/TypeScript UI, and Textual terminal interface.
- A Diagnostics screen with detailed component/subsystem health, scanner/learning/paper-trading metrics, persisted activity, bounded/redacted backend logs, frontend API and React render traces, actionable failure recommendations, and database-write counts grouped by table. Desktop backend logs rotate at 10 MiB with three retained backups. Frontend traces are retained in a bounded in-memory buffer and uploaded in small authenticated batches; SQL values and request query strings are not logged. High-frequency successful SQL mutations are summarized in 10-second windows, while write failures are logged immediately. Repeated candle collection failures are coalesced by symbol/timeframe and their recovery is recorded.

The diagnostics system traces operational boundaries and meaningful workflow stages; it does not instrument every private/helper function or log every market tick, DOM mutation, SQL value, or API payload. This bounded approach is intended to expose real defects without leaking credentials, overwhelming the UI, or degrading runtime performance.

Presence of a module or screen does not establish that it is enabled in a production configuration, operational against a live service, validated for financial use, or safe for multiple hosted users.

## Release-blocking findings

1. A Telegram token was present in `.env.example`. The value was removed and Telegram is disabled in the template. Revoke the exposed token, search any published source history/artifacts, and configure replacements only in private runtime configuration.
2. Adaptive drawdown/correlation calculations no longer return fixed placeholders. Drawdown requires persisted high-water-mark evidence; correlation requires aligned, validated return observations. The main simulator does not currently supply all this evidence to the adaptive assessment, so those factors can remain unavailable.
3. This workspace has uncommitted changes based on `466dbc7`. Establish a reviewed source commit and run CI/release checks against that exact commit.
4. A new current-source installer now includes the PyInstaller backend bundle, but self-contained operation is not accepted until this exact artifact passes install/readiness/local-authentication/duplicate-launch/graceful-close/upgrade/data-preservation/uninstall checks on a clean Windows system with Python removed from `PATH`.
5. The legacy Next.js source was not approved for production: its shared backend had no account-level authorization or tenant isolation. Production build/start scripts and the hosted CI/deployment workflow have been removed; the source remains only in the working tree and is not packaged with desktop releases.
6. No live production Binance stream or financial performance result was verified. The current installer is explicitly unsigned; no valid code-signing certificate or `signtool.exe` was available in the local environment.
7. Git tracks local database-related files, backup archives, and generated `blackmarket-web/.next` output. Review and remove these safely from version control before publication; `.gitignore` does not untrack existing files.

## Additional work before release

- Verify local REST API and WebSocket authentication independently, CORS origin allowlists, production Tauri CSP, child-process cleanup, per-process shutdown authorization, and public `/health` content on the exact release build.
- Add integration checks for freshness rejection, stream failure/recovery, order lifecycle/restart recovery, and duplicate event/notification behavior.
- Validate backup restore and corrupted-database recovery on disposable copies; document that SQLite/model/backup data is not application-encrypted.
- Repeat Python and locked desktop dependency scans on the committed release source and inspect built artifacts for secrets. The current workspace has no Telegram-token-shaped value, but a targeted local history scan found one in commit `0415b531e14efa7e03c932a6c1e7ee8492105179`; external history and release artifacts remain unchecked. Review workflow permissions and third-party action pins.
- Complete manual Tauri UI and keyboard acceptance, extend browser coverage to remaining workflows, resolve lint warnings, and measure frontend chunk splitting before treating the UI as fully accepted.
- Verify legal distribution terms, third-party notices, privacy/data handling, support scope, installer signature status, artifact hash, and release notes.
- `pyproject.toml` requires Python 3.12+ and registers the `live` marker. Python 3.13 passed locally; run the suite on Python 3.12 before claiming both CI matrix versions are validated. Investigate the Starlette/httpx TestClient deprecation.

## Product constraints

- Paper trading only. `REAL_TRADING_ENABLED=true` is rejected at startup; Binance private API key/secret configuration was removed.
- Exchange data depends on Binance availability, network reachability, rate limits, and exchange schema changes.
- Risk controls and simulated results are for research; they do not establish profitability or protect real funds.
- SQLite files, models, and backups are not encrypted by the application.

Detailed findings and severity are recorded in `LOCAL_AUDIT_REPORT.md`.
