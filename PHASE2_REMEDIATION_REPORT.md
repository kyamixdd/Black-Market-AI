# Phase 2 Remediation Report

## Result

Phase 2 code remediation and regression verification were completed before native Windows tooling was available. The original Phase 2 results and limitations below are historical; subsequent native build and runtime verification are recorded in the Phase 3 addendum at the end of this report. The existing Python trading engine, React frontend, FastAPI adapter, SQLite data, and paper-only trading boundary were retained.

## Findings and remediation

| Task | Root cause / finding | Fix | Verification |
|---|---|---|---|
| 1. Local API and WebSocket security | REST routes and WebSockets did not consistently authenticate a local client; desktop origin policy and CSP needed enforcement. | `src_tauri/backend/main.py` now limits the adapter to loopback, protects `/api/*` with bearer auth and WebSockets with token auth before subscription, restricts CORS, and keeps public `/health` limited to supervisor readiness. Tauri `src-tauri/src/backend.rs` and `lib.rs` provide a per-process token through IPC; `tauri.conf.json` supplies a restrictive CSP. | Full Python suite passed, including separate authorized/unauthorized REST, WebSocket, CORS, and internal-shutdown authorization tests. Frontend production build passed. |
| 2. Production disaster recovery | `DisasterRecoveryOrchestrator` was not connected to the production orchestrator lifecycle; async shutdown callbacks could be discarded. Open paper state and order recovery/persistence were incomplete. | `core/orchestrator.py` constructs recovery during production startup, registers position/order persistence handlers, and starts recovery. `core/disaster_recovery.py` restores open positions and open orders by ID, recovers balances/daily realized P&L, schedules verified backups, and starts watchdog/reconnect managers. `database/repositories.py` commits trade history and position closure in one transaction. `core/event_bus.py` drains queued events during shutdown, and shutdown now awaits awaitables returned by handlers. | Full suite passed; focused Phase 2 + disaster recovery tests: **34 passed**. Existing tests cover backup, backup verification/restoration, recovery idempotence, reconnection callback behavior, and startup/shutdown. |
| 3. Release script safety | The prior script could remove the project-root `dist` tree and risk existing release artifacts. | `build_release.ps1` uses a dedicated `release-output`, refuses to overwrite an existing version, excludes runtime/development/secrets, and supports `-DryRun`. | Dry-run created no directory or files. SHA-256 comparison confirmed all **98** root `dist` files were unchanged. No destructive release operation was run. |
| 4. Dashboard readiness | Null or incomplete market responses could appear loaded and permit chart-ready UI. | `blackmarket-desktop/src/App.tsx` and `src/services/marketData.ts` require a matching market snapshot and valid candles and distinguish backend connectivity from market-data readiness. Missing data does not produce fallback prices. | Frontend market-data tests: **4 passed**, including failed/missing readiness data and valid response cases. Production build passed. |
| 5. Chart reset and historical loading | Chart state identity omitted market type/timeframe; historical paging could duplicate, reorder, or include unfinished candles. | `LiveMarketChart.tsx` uses symbol + Spot/Futures + timeframe identity. Historical loading uses a cursor, filters unfinished candles, merges/deduplicates, preserves order, and guards concurrent requests. | Frontend tests verify market/timeframe key switching and candle sorting/deduplication; production build passed. |
| 6. Portfolio and settings | Financial labels/calculations used misleading periods/baselines and settings writes could imply unsupported behavior. | `orchestrator_bridge.py` calculates realized UTC daily/monthly P&L, separates realized/unrealized values and Spot/Futures accounts, uses simulator baselines, and reports the active risk manager limit. Settings GET does not expose Telegram secrets; unsupported writes return HTTP 501. | Portfolio and settings tests verify configurable baselines, UTC period boundaries, actual risk limit, secret omission, and 501 behavior. |
| 7. Stale frontend integrations | Unused API prefixes/components could drift from the active adapter; one assistant component contained fabricated sample responses. | Corrected API paths/health usage and removed the unused fabricated assistant component. The active assistant continues to use local BlackMarket AI data. | TypeScript production build and frontend tests passed. |
| 8. Warning audit | Test suite emitted warnings that needed classification rather than blanket suppression. | No warning suppression was added. Third-party Python deprecations and existing frontend lint warnings are documented below and in `DEVELOPMENT_PROGRESS.md`. | Full Python suite: **278 passed, 200 warnings**. |
| 9. Regression suite | Existing functionality and safety controls needed regression verification after fixes. | Added focused Phase 2 tests and ran the complete Python and frontend checks. Existing trade-history records are retained; real Binance trading was not introduced. | Python **278 passed**; frontend tests **4 passed**; build passed; lint exited 0 with existing warnings. |
| 10. Report and stop | Remediation results and remaining gaps needed persistent documentation. | Updated `DEVELOPMENT_PROGRESS.md`, the applicable `.claude/skills/*/SKILL.md` guidance, and this report. Native packaging was not started in this phase. | Documentation reflects executed checks and explicit remaining limitations. |

## Warning classification

### Python — 200 warnings

- **FastAPI/Starlette deprecation warnings:** 199 warnings report `asyncio.iscoroutinefunction` usage under Python 3.14; this is in installed framework code (`fastapi/routing.py` and `starlette/_utils.py`).
- **Starlette TestClient / AnyIO deprecation:** 1 warning reports the deprecated `anyio.abc.BlockingPortal` alias.
- No application async-lifecycle, resource, or runtime warning appeared in the full suite. Framework warnings were not suppressed or patched in vendored code.

### Frontend lint

`npm run lint` exits 0. Existing warnings remain for unused identifiers and React hook/effect patterns in the store, legacy panels, and `MarketChart.tsx`. They were not expanded into unrelated frontend cleanup.

## Changed-file groups

- **API security / Tauri token / CSP:** `src_tauri/backend/main.py`, `blackmarket-desktop/src-tauri/src/backend.rs`, `blackmarket-desktop/src-tauri/src/lib.rs`, `blackmarket-desktop/src-tauri/tauri.conf.json`, `blackmarket-desktop/src/services/localAuth.ts`, `api.ts`, `websocket.ts`.
- **Dashboard / chart data integrity:** `blackmarket-desktop/src/App.tsx`, `components/charts/LiveMarketChart.tsx`, `services/marketData.ts`, `services/marketData.test.ts`, and related styles/package test script.
- **Recovery / persistence / accounting:** `core/orchestrator.py`, `core/disaster_recovery.py`, `core/event_bus.py`, `database/repositories.py`, `paper_trading/simulator.py`, `src_tauri/backend/bridge/orchestrator_bridge.py`, and related API routes/schemas.
- **Release safety:** `build_release.ps1`.
- **Assistant cleanup:** removed `blackmarket-desktop/src/components/AIAssistant/ChatInterface.tsx`, an unused component with fabricated sample responses.
- **Tests:** `tests/test_backend_api.py`, `tests/test_desktop_settings.py`, `tests/test_paper_trading_phase5.py`, `tests/test_phase2_remediation.py`, plus existing disaster recovery and EventBus tests.
- **Guidance:** relevant architecture, Binance, code-audit, database, documentation, paper-trading, QA, and risk skill files were updated. Other skill files were reviewed and left unchanged where Phase 2 did not alter their domain.

## Remaining limitations

1. **Production exchange streams:** the market scanner currently polls public REST endpoints. Production Binance stream subscriptions are not configured. The reconnection helper is tested with a fake managed stream, not a live production connection.
2. **Watchdog response:** heartbeat stalls are logged; the watchdog does not restart the backend.
3. **Process-level recovery:** deterministic in-process integration tests cover recovery and graceful shutdown. A forced backend crash/restart with a running Tauri desktop was not exercised.
4. **Local security model:** loopback, per-process token auth, Tauri IPC, CORS, and CSP protect against unrelated local clients. They do not isolate the application from malicious code running as the same Windows user or from a compromised webview.
5. **Settings writes:** `POST /api/settings` deliberately returns HTTP 501; settings mutation is unsupported and risk ceilings cannot be changed through this endpoint.
6. **Account baseline persistence:** configured simulator baselines are used; a user-adjustable account baseline is not persisted as separate account state.
7. **Native Windows release:** native Tauri compilation, packaged-resource paths, NSIS install, startup readiness, and graceful desktop shutdown remain unverified. Rust/Cargo are absent; Visual Studio 2022 Build Tools is installed without the required MSVC C++ tools/Windows SDK. No native package was built as part of this remediation.

## Windows build environment assessment

Checked the host without installing packages or modifying the existing Python environment:

| Dependency | Result |
|---|---|
| Python | Python 3.14.7 is installed and is the only `py` interpreter listed. No project `venv`/`.venv` is present. `fastapi==0.115.0` and `httpx==0.27.0` are installed; `uvicorn` is missing. Installed SQLAlchemy, aiosqlite, and Pydantic versions differ from the exact pins in the repository requirements, so do not run the full pinned requirements file against the existing global interpreter. |
| Node.js / npm | Node 24.19.0 and npm 11.17.0 are installed. Local `@tauri-apps/cli` 2.12.5 and `@tauri-apps/api` 2.12.5 are installed. |
| Rust / Cargo | `rustup`, `rustc`, and `cargo` are not installed/on PATH. `Cargo.toml` requires Rust 1.90 or newer. |
| Microsoft C++ Build Tools | Visual Studio 2022 Build Tools is installed, but its instance does not include detected MSVC C++ tools or Windows SDK components. `cl.exe` is not available. |
| WebView2 | Evergreen Runtime 157.0.4341.60 is installed and recognized by the Tauri CLI. |
| Windows | Windows 10 build 19045 (x64). |

### Tauri configuration check

The locally installed `tauri info` command completed without compiling and parsed the app configuration. It reports `frontendDist: ../dist`, `devUrl: http://localhost:3000/`, the configured restrictive CSP, Tauri 2.12.6, and the NSIS bundle target. The frontend distribution, config schema, installer icon, and all configured Python resource roots exist. `vite.config.ts` uses port 3000, matching `devUrl`. No Tauri configuration blocker was found. The CLI reports `@tauri-apps/plugin-log` JavaScript bindings are absent, but the app does not import those bindings; the Rust plugin is only used for debug logging.

### Required installation steps

1. **Complete the existing Visual Studio Build Tools installation.** Open Visual Studio Installer, choose **Modify** for the installed Visual Studio 2022 Build Tools instance, select **Desktop development with C++**, and ensure **MSVC v143 x64/x86 build tools** and a **Windows 10 or Windows 11 SDK** are selected. Apply the changes and reopen the terminal. If the installer is unavailable, download it from [Microsoft C++ Build Tools](https://aka.ms/vs/17/release/vs_BuildTools.exe). These components provide the MSVC linker/compiler and Windows SDK required by Rust's `x86_64-pc-windows-msvc` target and Tauri.
2. **Install Rust via the official rustup installer.** In PowerShell, after step 1:

   ```powershell
   $rustupInstaller = Join-Path $env:TEMP 'rustup-init.exe'
   Invoke-WebRequest -Uri 'https://win.rustup.rs/x86_64' -OutFile $rustupInstaller
   & $rustupInstaller -y --default-host x86_64-pc-windows-msvc --default-toolchain stable
   ```

   Restart the terminal, then verify `rustc --version` and `cargo --version`. This adds the required compiler and package manager without changing Python.
3. **Add the missing backend server dependency without replacing the global Python installation.** The supervisor automatically checks the project `.venv` and supports `BLACKMARKET_PYTHON`. To reuse currently installed Python packages while isolating the missing dependency:

   ```powershell
   Set-Location 'C:\Users\MARIA\Documents\BlackMarket AI'
   py -3.14 -m venv --system-site-packages .venv
   .\.venv\Scripts\python.exe -m pip install 'uvicorn[standard]==0.30.0'
   .\.venv\Scripts\python.exe -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"
   ```

   This creates a repository-local environment and leaves the existing global Python packages unchanged. The project pins Uvicorn 0.30.0 in `src_tauri/backend/requirements.txt`. Do not install the entire pinned requirements file into the existing global interpreter; it would alter packages already present. The `.venv` is automatically considered by the desktop supervisor.

4. **No WebView2 installation is needed.** The runtime is already detected.

After prerequisites are installed, verify `rustup show`, `rustc --version`, `cargo --version`, `cl.exe` from a Visual Studio Developer PowerShell, and the Python import command above. Only then attempt `npm run tauri:build`. Native compilation has not been attempted in this environment assessment.

## Phase 3 follow-up — Native build and installed runtime (2026-11-17)

This addendum supersedes the Phase 2-era native-build limitations above. Rust stable, Cargo, MSVC/Windows SDK, and WebView2 were subsequently available; the final `npm run tauri:build` completed and produced:

- `blackmarket-desktop\src-tauri\target\release\app.exe`
- `blackmarket-desktop\src-tauri\target\release\bundle\nsis\BlackMarket AI_1.0.0_x64-setup.exe` (2.14 MiB)

The package was freshly installed to an isolated temporary directory and launched using the project `.venv` via `BLACKMARKET_PYTHON`. With no Telegram credentials and no Telegram enable flag, `/health` reported backend, database, WebSocket manager, scanner, and paper-trading readiness. The app presented a native “BlackMarket AI” window; its executable metadata and associated icon were checked.

Runtime checks confirmed:

- Backend listener bound only to `127.0.0.1`; unauthenticated `GET /api/markets` returned HTTP 401.
- Authenticated desktop heatmap and market-breadth requests returned HTTP 200 after adding the repository method used by their persisted-snapshot fallback.
- A second app launch did not add another desktop process or API listener.
- Native window close completed backend lifespan shutdown and closed port 8765.
- The configured per-user data directory held the database and verified compressed shutdown backup; no backup was written under the installation directory. Database and backup `PRAGMA integrity_check` results were `ok`, and paper-position/order/trade counts were unchanged.
- The final runtime produced no application errors or HTTP 500s after startup. Expected WebSocket peer-close races are handled without an ASGI application error.

The installed launch exposed and fixed three prior gaps: Telegram's code default contradicted the shipped `.env.example`; dashboard heatmap/breadth fallback called missing `Repository.get_recent_snapshots`; and disaster recovery used a relative backup path rooted in the install working directory. A WebSocket send/disconnect race was also reproduced and handled with a state-checked close path.

Final full Python suite: **282 passed, 200 third-party deprecation warnings**. The frontend TypeScript/Vite build, Rust release build, and NSIS bundling passed. No warnings were suppressed.

### Phase 3 limitations

- The NSIS bundle does not include Python or the backend dependency environment. Runtime success used this host's project `.venv`; Python 3.10+ and the backend requirements must be provisioned on other machines.
- Custom React window controls were not click-tested and the UI was not visually compared with the reference; the native window and OS close path were exercised.
- Forced process-crash/restart and clean-machine installation were not tested.
- Production exchange scanning still uses REST polling, without configured Binance exchange-stream subscriptions; watchdog stalls are logged rather than automatically restarted.

