# Security Policy and Threat Model

Last reviewed: 25 November 2026
Evidence: local workspace source review at commit `466dbc7` with uncommitted changes. No remote CI evidence was verified.

## Security scope

BlackMarket AI is a local-first market research and **paper-trading-only** application. It uses public Binance market-data endpoints and simulates orders locally. The application is not intended to submit real exchange orders.

The supported production path is the Tauri desktop application with a supervised local FastAPI backend. No web application or hosted web frontend is part of the supported product.

## Current release security findings

- `.env.example` contained a non-placeholder Telegram bot token. The value has been removed from the template and Telegram is disabled there by default. A targeted local history scan found a token-shaped value in root `.env.example` at commit `0415b531e14efa7e03c932a6c1e7ee8492105179`; the token itself is not reproduced. Treat it as compromised: revoke it through BotFather, configure any replacement only in a private environment, and assess history cleanup if that commit was published. External history and release artifacts have not been checked.
- `REAL_TRADING_ENABLED=true` is now rejected during startup validation. Binance API key/secret configuration was removed; the application uses public market-data endpoints and paper execution only.
- Local test/build checks passed as listed in `docs/PROJECT_STATUS.md`; this does not establish a fresh dependency audit, a security certification, production stream availability, or a release-candidate review.

## Security invariants

- No Binance private trading credentials are required for market data.
- The paper-trading simulator is the only order execution target in the documented product scope.
- No live order signing or real-money exchange order execution is part of this application.
- ML models do not directly change the configured risk limits.
- Model promotion must be gated by chronological/out-of-sample validation and the current promotion-evidence checks; a model being trained or registered does not mean it is promoted.
- Stale or insufficient market data should be surfaced as unavailable/rejected rather than treated as a valid fresh signal.
- Telegram is optional and disabled by default. Its bot token is a secret.

## Network boundaries

### Desktop/local API

- The API binds to loopback by default, normally `127.0.0.1:8765`.
- API routes require a bearer token. The token is compared using a constant-time comparison.
- Remote clients are rejected unless `BLACKMARKET_REMOTE_API_ENABLED=1` is explicitly set.
- WebSocket connections are authenticated and rate-limited.
- The desktop supervisor manages the backend lifecycle; the backend should not be exposed directly to the public internet in the default configuration.
- Packaged Tauri configuration permits the loopback backend but excludes Vite's `localhost:3000` WebSocket origins. Those development-server origins are added only by `tauri.dev.conf.json` through the `tauri:dev` command.
- The API token is stored in desktop app data and is made available to the local Tauri frontend; the separate shutdown token is generated per backend process and is not exposed to the frontend. Neither protects against malicious code running as the same Windows user or a compromised desktop webview.
- The Vite development server is used only as the embedded frontend build/runtime for the Tauri desktop shell. Do not expose it as a standalone web application or use it to host the backend.


## Rate limiting limitations

API and WebSocket rate limits are implemented as process-local in-memory controls. They reset when the process restarts and are not shared between multiple backend instances. For a multi-instance or public remote deployment, configure an upstream gateway or shared rate limiter; do not rely on process-local counters as distributed abuse protection.

## Data protection

- SQLite database files are **not encrypted by the application**.
- Backup archives are also not application-encrypted.
- Protect database, model, configuration, and backup directories using OS-level full-disk encryption and restrictive filesystem permissions.
- Keep `.env` out of version control. Do not place credentials in source code, issue reports, screenshots, or diagnostic bundles.
- The project may store paper-trading history, settings, model artifacts, and logs locally. Treat these as user data and back them up appropriately.
- Do not assume logs contain no sensitive values; review logging changes before release.

## External services and data flow

Expected external services:
- Binance public REST and market WebSocket endpoints for market data.
- Telegram Bot API only when the optional notification feature is enabled.
- An operator-configured OpenAI-compatible endpoint for assistant interpretation, only when explicitly enabled.

The application does not need a Binance account or trading API key for public market data. Public market data is still subject to exchange availability, rate limits, and changes to exchange APIs.

The optional assistant provider receives the user's question (up to 500 characters) and the selected deterministic evidence result serialized as JSON (up to 12,000 characters). Depending on the selected tool, that evidence can contain portfolio balances, open positions, closed paper-trade history, risk status, strategy metrics, or learning results. Provider use is disabled by default. When enabled, configure the endpoint and any key only in the backend environment; the configured provider can process and retain submitted data according to its own terms. Request bodies, endpoint URLs, and API keys must not be logged.

## Dependency and build security

Before publishing a release:

- Review Python requirements, npm lockfiles, and Rust/Tauri dependencies for changes.
- Run dependency vulnerability checks (for example, `pip-audit` and `npm audit`) and triage findings.
- Review GitHub Actions workflow permissions and third-party actions.
- Build release artifacts from a known commit in a controlled workflow.
- Verify the artifact hash and release notes.
- Sign the Windows installer if signing infrastructure is available; clearly disclose if the artifact is unsigned.
- Do not publish a CI artifact as a stable release without release acceptance.

A clean dependency scan or successful CI run is not a security certification.

## Threats and limitations

| Threat | Current mitigation | Remaining limitation |
|---|---|---|
| Accidental real trading | Paper-only simulator and no documented exchange order path | Re-check code and dependencies before each release |
| Local API access | Loopback binding, bearer token, rate limits | Local malware or a compromised user account can access local resources |
| Remote API exposure | Disabled by default; token required when enabled | Requires TLS, ingress restrictions, and deployment-specific review |
| Brute-force/abuse | Process-local rate limits | Counters reset and are not distributed |
| Database loss/corruption | Integrity checks and backups | Backups are not encrypted; restore must be tested |
| Dependency compromise | Lockfiles/pinned dependencies where provided; CI | Supply-chain risk is not eliminated |
| Model overfitting | Chronological validation and promotion gates | Validation does not guarantee future profitability |

## Security checklist before release

- [ ] Verify no real exchange order endpoints or trading credentials were introduced.
- [ ] Verify no secrets are committed; rotate any exposed secret immediately.
- [ ] Confirm `.env` and local data are excluded from version control.
- [ ] Confirm desktop API is loopback-only by default and unauthenticated requests fail.
- [ ] Confirm remote API mode is off unless explicitly required and secured.
- [ ] Verify origin checks and proxy throttling with tests.
- [ ] Run dependency and secret scans; review results rather than treating “no findings” as proof.
- [ ] Verify database integrity, backup creation, and restore on a disposable copy.
- [ ] Verify the Windows installer starts and shuts down correctly on a clean Windows environment.
- [ ] Verify artifact version, hash, release notes, signing status, and upgrade/uninstall behavior.

## Incident response

If a secret is exposed:
1. Revoke or rotate it immediately (Telegram token via BotFather; any exposed backend or assistant-provider secrets in private runtime configuration).
2. Remove the exposed value from active configuration and restart affected services.
3. Review logs and deployment history for misuse.
4. Avoid posting the replacement secret in a public issue or commit.

If database corruption or unexpected behavior occurs:
1. Stop the application.
2. Preserve a copy of the database and SQLite sidecar files.
3. Preserve logs and the relevant commit/version.
4. Test recovery using a backup copy; do not delete the only original database.

## Reporting a vulnerability

Exploit details and secrets must not be included in public issues. Submit vulnerability reports through GitHub private vulnerability reporting when enabled. Otherwise, use a private contact channel listed in the repository maintainer's GitHub profile. Reports should include the affected commit/version, impact, and minimal reproduction. Live credentials and private user data must be excluded.

No response-time SLA or security certification is implied.

## Release notes

This policy describes the intended current architecture and its known limitations. Review the actual release commit and deployment configuration before relying on any statement for a specific release.
