# Project Status and Audit

Review date: 24 November 2026  
Product version: `1.0.0`  
Release classification: desktop beta candidate; website private preview  
Source identity: not verified. The local Git repository has no commits and all application files are uncommitted.

## Assessment

**Overall score: 6.0/10 — functional beta; not ready for unrestricted public release.**

The score is an engineering-readiness assessment, not a financial-performance rating. It reflects source breadth, current local test/build evidence, safety defects, operational verification, and release provenance.

| Area | Score | Evidence |
|---|---:|---|
| Shared frontend | 7.0/10 | Production build and 8-viewport browser smoke pass; lint reports maintainability and hook warnings; complete Tauri UI acceptance remains open |
| Python backend and API | 7.5/10 | Backend regression suite passes on Python 3.13; desktop API has bearer authentication, loopback checks, restricted CORS, and authenticated WebSocket setup |
| Market data | 6.0/10 | Public Spot/Futures REST scanning is implemented; stream manager exists but production scanner subscriptions are not configured |
| Paper trading and risk | 6.0/10 | Simulated order lifecycle and atomic close persistence exist; adaptive drawdown/correlation are calculated only when validated evidence is supplied |
| Learning and research | 6.5/10 | Walk-forward validation, outcome records, model lifecycle and promotion gates exist; no fresh training or performance validation was run |
| Persistence and recovery | 7.0/10 | SQLite integrity checks, backup/recovery paths, and ID-based position recovery exist; database and backup confidentiality is not provided |
| Desktop packaging | 5.0/10 | Tauri supervisor and installer workflow exist; no installer was built or accepted in this workspace |
| Hosted website | 4.0/10 | Login/session and same-origin proxy tests pass; shared-password identity, tenant isolation, durable hosting, and production smoke tests remain absent |
| Automated verification | 8.0/10 | 669 Python tests, 16 desktop service tests, 8 website security tests, dependency scans, and frontend builds pass; three live exchange tests were deselected |
| Public release readiness | 3.5/10 | No source commit, release artifact, signing evidence, current-head CI, or clean-machine acceptance |

## Verification run in this workspace

- `.\.venv\Scripts\python.exe -m pytest -q -m "not live"`: 669 passed, 3 live tests deselected. Starlette emits an httpx TestClient deprecation warning.
- Backend `pip-audit -r src_tauri\backend\requirements.txt`: no known vulnerabilities; `pip check`: no broken requirements.
- Desktop and website npm audits reported zero vulnerabilities.
- A Python wheel built and installed into an isolated target; expected `benchmarks`, `risk`, `monitoring`, and `src_tauri.backend` imports passed from a clean working directory on Python 3.13. Python 3.12 CI verification remains pending.
- `blackmarket-desktop`: `npm test` passed 16 tests; `npm run build` passed; `npm run lint` completed with warnings.
- Responsive browser smoke passed at 8 widths from 320 to 1920 pixels, checking horizontal overflow, primary navigation, chart-settings interaction, and page errors.
- `blackmarket-web`: `npm ci`, 8 security tests, TypeScript check, dependency audit, and production build passed; npm audit reported zero vulnerabilities.
- Website build completed without the prior Windows SWC fallback warning.
- The desktop frontend build emitted a 500 kB chunk-size warning.
- The Tauri installer, native application launch, production exchange streams, hosted backend, backup restore, and full manual UI workflows were not verified in this audit.

## Implemented product areas

- Public Binance Spot and USDⓈ-M Futures market discovery, REST data, candles, scanner, and stream-management code.
- Technical analysis, multi-timeframe signals, market breadth, volume, long/short, regime, and data-freshness checks.
- Strategy families, Strategy Lab, historical backtesting, comparison, and saved research reports.
- Paper Spot/Futures orders and positions, simulated fees/slippage/funding, leverage/liquidation handling, and persisted trade history.
- Runtime risk limits, paper-trading readiness checks, and settings validation.
- Prediction outcomes, model registry, confidence calibration, chronological validation, promotion and rollback gates.
- Market intelligence, assistant, research, strategy evolution, drift monitoring, trade review, workspaces, public strategy library, and shareable analysis.
- SQLite persistence, integrity checks, backups, restore, event persistence, and recovery routines.
- Tauri desktop, shared React/TypeScript UI, Next.js private-preview frontend, and Textual terminal interface.

Presence of a module or screen does not establish that it is enabled in a production configuration, operational against a live service, validated for financial use, or safe for multiple hosted users.

## Release-blocking findings

1. A Telegram token was present in `.env.example`. The value was removed and Telegram is disabled in the template. Revoke the exposed token, search any published source history/artifacts, and configure replacements only in private runtime configuration.
2. Adaptive drawdown/correlation calculations no longer return fixed placeholders. Drawdown requires persisted high-water-mark evidence; correlation requires aligned, validated return observations. The main simulator does not currently supply all this evidence to the adaptive assessment, so those factors can remain unavailable.
3. This workspace has no commit history and all files are uncommitted. Establish a reviewed source commit and run CI/release checks against that exact commit.
4. The Tauri installer and lifecycle checks have not been run as part of this audit. Verify install, readiness, local authentication, duplicate launch, graceful close, upgrade, data preservation, and uninstall on clean Windows systems.
5. The website is a shared-password private preview. It has no per-user identity or account/data isolation. Keep it private until identity, authorization, tenant isolation, durable storage, rate-limit/session sharing, and hosted recovery are implemented and tested.
6. No production Binance stream, hosted backend, release signing, or financial performance result was verified.

## Additional work before release

- Verify local REST API and WebSocket authentication independently, CORS origin allowlists, production Tauri CSP, child-process cleanup, per-process shutdown authorization, and public `/health` content on the exact release build.
- Add integration checks for freshness rejection, stream failure/recovery, order lifecycle/restart recovery, and duplicate event/notification behavior.
- Validate backup restore and corrupted-database recovery on disposable copies; document that SQLite/model/backup data is not application-encrypted.
- Repeat Python and locked website dependency scans on the committed release source and inspect built artifacts for secrets. A local scan found no Telegram-token-shaped values in the workspace; it cannot establish external history or artifact status. Review workflow permissions and third-party action pins.
- Complete manual Tauri UI and keyboard acceptance, extend browser coverage to remaining workflows, resolve lint warnings, and measure frontend chunk splitting before treating the UI as fully accepted.
- Verify legal distribution terms, third-party notices, privacy/data handling, support scope, installer signature status, artifact hash, and release notes.
- `pyproject.toml` requires Python 3.12+ and registers the `live` marker. Python 3.13 passed locally; run the suite on Python 3.12 before claiming both CI matrix versions are validated. Investigate the Starlette/httpx TestClient deprecation.

## Product constraints

- Paper trading only. `REAL_TRADING_ENABLED=true` is rejected at startup; Binance private API key/secret configuration was removed.
- Exchange data depends on Binance availability, network reachability, rate limits, and exchange schema changes.
- Risk controls and simulated results are for research; they do not establish profitability or protect real funds.
- Website rate limits and session revocation are process-local. Do not deploy the current shared-password website as a multi-user service.
- SQLite files, models, and backups are not encrypted by the application.

Detailed findings and severity are recorded in `AUDIT_REPORT.txt` at the repository root.
