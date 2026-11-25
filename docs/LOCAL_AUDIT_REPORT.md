# Desktop-Only Production Audit

Review date: 25 November 2026
Workspace: `C:\Users\MARIA\Desktop\Black-Market-AI-Beta`  
Product version: `1.0.0`  
Source baseline: `466dbc7` on `Black-Market-AI-Beta-1.0.1`, with pre-existing uncommitted changes

## Executive summary

The application is a local-first, paper-trading desktop product. The desktop release path and core safety boundaries were reviewed, and the supported hosted-web release path was removed. The legacy Next.js source and generated build output remain in the working tree; this is a release-path removal, not a deletion of all web source.

No evidence was found in the reviewed exchange-client paths of Binance private order endpoints, API-key signing, or automatic real-money execution. Local API authentication, WebSocket authentication, loopback restrictions, allowed origins, Tauri CSP, shutdown authorization, SQLite trade-close transactions, ID-based recovery, data freshness gates, and model-promotion evidence checks were reviewed. These controls do not establish that the application is safe for financial use or that every code path is defect-free.

**Overall assessment: functional desktop beta; not ready for unrestricted public release.** The most material unresolved repository risk is that local runtime databases, backups, and generated Next.js output are tracked in Git. They may include user data and should not be distributed casually. The pre-existing worktree changes were preserved; no files were bulk-deleted or untracked.

## Findings by severity

### High — Local runtime databases, backups, and generated web output are tracked

**Evidence:** Git tracks 3 database-related files, 86 backup files, and 124 files under `blackmarket-web/.next`. The `.gitignore` now excludes future `data/backups/`, `data/*.db*`, and `models/*.pkl` additions, but ignore rules do not stop tracking files already in the Git index. The `.next` directory is generated production build output.

**Impact:** Database and backup files may contain paper-trading history, settings, model or other local state. Their contents were not inspected for private user data. Tracked files can be included in future commits or source archives; ignore rules do not remove copies from Git history.

**Recommendation:** Before any publication, review the tracked files and their history. Preserve any needed local data outside the repository, then separately remove runtime data and generated build output from version control and consider history cleanup if sensitive data was ever published. This was not done in this audit to avoid deleting or overwriting pre-existing user work.

### High — Previously exposed Telegram bot token requires revocation confirmation

**Evidence:** A non-placeholder Telegram bot token was previously present in `.env.example` and has since been removed. The current template contains only an empty setting. A targeted scan of the 16 local commits affecting the root and web environment templates found a token-shaped value in root `.env.example` at commit `0415b531e14efa7e03c932a6c1e7ee8492105179`. The value is not reproduced here. External publication history and release artifacts were not checked.

**Impact:** If the token remains active or exists in any published history/artifact, another party may use it to operate the associated bot.

**Recommendation:** Revoke the exposed token through BotFather, configure any replacement only in private runtime configuration, and assess history cleanup if that commit was published. Check external Git history and release artifacts separately. Do not publish token values in reports or logs.

### Medium — Legacy web application code and production artifacts remain

**Evidence:** The hosted smoke workflow and website CI production-build/dependency-audit job were removed. The `blackmarket-web/package.json` no longer defines `build` or `start` scripts. However, the Next.js source, dependencies, and tracked `.next` output remain in the working tree. The shared hosted backend path was not designed with account-level authorization or per-user data isolation.

**Impact:** Web hosting is no longer a supported or automated release target, but the web implementation has not been physically removed. Retained source or generated output could still be manually invoked, and must not be exposed as a multi-user hosted service.

**Recommendation:** Keep the web app out of production and desktop packaging. If “remove completely” is intended to mean deleting all web source and build output, do that as a separately reviewed change after preserving the pre-existing edits in `blackmarket-web/`; do not deploy the retained code.

### Medium — Event-bus overflow drops events

**Evidence:** `core/event_bus.py` uses a bounded queue and catches `asyncio.QueueFull`, increments a dropped counter, and logs a warning rather than blocking or retrying.

**Impact:** Under sustained overload, subscribers may miss notifications or state updates. Whether an event is persisted and replayable depends on the event type and persistence path; the queue-drop warning alone does not provide delivery guarantees.

**Recommendation:** Classify critical versus best-effort events, define backpressure or durable retry behavior for critical events, and expose dropped-event metrics/alerts.

### Medium — Watchdog reports stalls but does not recover components

**Evidence:** `core/disaster_recovery.py` invokes `_on_stall`; the handler explicitly logs that automatic watchdog recovery is not implemented.

**Impact:** A stalled component can remain stalled while the operator receives a log message. Recovery requires external or manual action; configuration naming should not be interpreted as evidence that watchdog restart works.

**Recommendation:** Implement supervised, bounded restart and health-state transitions with duplicate-start protection, or document watchdog behavior strictly as detection/alerting.

### Medium — Adaptive risk factors may be unavailable in the simulator path

**Evidence:** `risk/adaptive_risk.py` requires persisted high-water-mark evidence for drawdown and aligned validated return observations for correlation. The main simulator does not currently supply all evidence to the adaptive assessment.

**Impact:** These factors correctly avoid fabricated values, but can remain unavailable during ordinary simulation. Any risk view relying on them may therefore be incomplete.

**Recommendation:** Feed validated evidence into the assessment or clearly label the factors unavailable and prevent users from interpreting them as measured.

### Medium — Installer acceptance does not establish a self-contained release

**Evidence:** A 1.0.0 x64 NSIS package was built and its install, backend readiness, loopback authentication, duplicate-launch behavior, and graceful window-close path were exercised on this Windows host. That package still depended on the host's Python and backend dependencies. Visual/custom-button interaction was not manually verified. This evidence is for that artifact, not proof that the current dirty source produces a self-contained release.

**Impact:** A user may not be able to run the installer on a clean Windows machine without separately installed Python/dependencies. The full UI and the exact current release artifact remain unaccepted.

**Recommendation:** Build the current source and validate the exact installer on a clean Windows machine with Python removed from `PATH`; verify install, readiness, authentication, duplicate launch, graceful close, upgrade/data retention, uninstall, and visual/keyboard interaction. Do not describe a package as self-contained until this passes.

### Low — Test client emits a deprecation warning

**Evidence:** The Python regression run reports a Starlette/httpx TestClient deprecation warning.

**Impact:** This does not currently fail the test suite, but an upstream compatibility change may require test updates.

**Recommendation:** Track the supported Starlette/httpx versions and update the test client usage before the warning becomes an incompatibility.

## Reviewed safety and correctness controls

- **Exchange usage:** reviewed exchange-client paths use public market-data calls; no private Binance order endpoint or signed-order flow was found. `REAL_TRADING_ENABLED=true` is rejected. Paper simulation is the only supported execution mode.
- **Desktop API boundary:** REST and WebSocket authentication are independently checked; peer loopback restrictions and explicit CORS origins are present. Packaged Tauri CSP excludes development-server origins. `/health` is intentionally public and is used for readiness.
- **Process control:** the per-process shutdown token is not exposed to the frontend, and the backend supervisor owns child-process lifecycle. The desktop API token is available to the local Tauri frontend; it protects against unrelated local clients, not malicious code running as the same Windows account or a compromised webview.
- **Persistence and recovery:** completion persistence and position closure use one database transaction; recovery is keyed by persistent IDs and is designed to be idempotent.
- **Freshness and learning:** signal paths reject stale or insufficient data. Model promotion uses chronological/out-of-fold validation and evidence gates; this review did not run fresh training or establish model performance.
- **Market streams:** scanner code configures bounded ticker subscriptions after REST discovery. Live production stream health, interruption handling, and recovery were not exercised in this audit.
- **Secrets:** the non-placeholder Telegram token was removed from `.env.example` and Telegram is disabled there. Treat the exposed value as compromised and revoke it. A targeted local history scan found a token-shaped value in commit `0415b531e14efa7e03c932a6c1e7ee8492105179`; external publication/history was not checked.
- **Data protection:** SQLite files, backups, and model artifacts are not application-encrypted. Protect them using filesystem permissions and OS-level encryption.

## Verification performed

- Python regression suite: **670 passed, 3 live exchange tests deselected** on Python 3.13; Python 3.12 was not run locally.
- Desktop frontend: production build passed, **16 tests passed**, and lint completed with warnings. The main bundle is 561.01 kB and produces a chunk-size warning.
- Desktop `npm audit`: **0 vulnerabilities**.
- Python `pip-audit`: **no known vulnerabilities**; `pip check` found no broken requirements.
- `cargo check --locked`: passed. A Rust dependency vulnerability audit was not run.
- No live exchange, current-head CI, backup-restore, or new installer build was performed in this audit. Previous NSIS acceptance is limited to the artifact and interactions described above.

## Production scope and remaining boundary

The Tauri desktop application is the only supported production target. The hosted web release workflow and production build/start scripts were removed, but legacy Next.js source and tracked production output remain. This audit therefore confirms removal of the supported web production path, not physical removal of every web artifact.

The working tree contains pre-existing changes and was not committed or pushed. No destructive cleanup of tracked database, backup, or generated web artifacts was performed. See `PROJECT_STATUS.md`, `RELEASE_READINESS.md`, and `RELEASING_AND_HOSTING.md` for current release gates.

## Implementation Update — 25 November 2026

- Added a desktop Diagnostics screen with supervisor/API/database/WebSocket/scanner/learning/paper-trading status, persisted activity, and a bounded backend process-log tail. The log reader limits reads to 64 KiB and 200 lines, caps individual lines, and redacts common sensitive-field entries.
- Added rolling 60-second frontend HTTP request counts, failure counts, mean duration and p95 duration. The metrics contain no endpoint paths or query values. Diagnostics reuses the app's shared activity poll; it polls health every 10 seconds and process logs every 2 seconds only while visible.
- Added `scripts/generate_symbol_catalog.mjs`, `docs/SYMBOL_CATALOG.md` (2,619 source-level function candidates), and `docs/FEATURE_AUDIT.md`. Python definitions use AST parsing. TypeScript/Rust entries use documented source scans and may include false positives or omit macro-generated definitions; the catalog is not proof of function correctness or runtime status.
- Current verification: Python 3.13.17 backend suite **670 passed, 3 live deselected**; desktop services **17 passed**; Rust supervisor **5 passed**; desktop lint and production build passed. The frontend build retains the approximately 567 kB chunk-size warning.
- Built a current-source 1.0.0 x64 NSIS artifact: **63,416,271 bytes**, SHA-256 `058d20af3191d98a8b8edecdce2e9cf272a51e76cc119924ede1fa99ed1f7db1`. `release-output/` contains the matching checksum and provenance manifest, which correctly records `local-uncommitted` and `NotSigned`.
- No valid signing certificate/private-key pair or `signtool.exe` was available in the standard local environment. A prior installation and shared app-data directory exist, so clean install/uninstall acceptance was not run. The new artifact is built, not release-accepted or signed.
- No live exchange, performance-before/after, visual/keyboard Tauri, backup-restore, or current-head CI acceptance was performed. Existing broader dashboard polling intervals were not changed without runtime evidence.
