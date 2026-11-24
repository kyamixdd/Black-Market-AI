# Security Policy and Threat Model

Last reviewed: 23 November 2026  
Evidence: local workspace source review. The local Git repository has no commits and all application files are uncommitted; branch/commit history and remote CI evidence were not verifiable.

## Security scope

BlackMarket AI is a local-first market research and **paper-trading-only** application. It uses public Binance market-data endpoints and simulates orders locally. The application is not intended to submit real exchange orders.

The supported primary path is the Tauri desktop application with a local FastAPI backend. The Next.js website is a private-preview deployment path and has a different server-side session/proxy boundary.

## Current release security findings

- `.env.example` contained a non-placeholder Telegram bot token. The value has been removed from the template and Telegram is disabled there by default. Treat the exposed token as compromised: revoke it through BotFather, configure any replacement only in a private environment, and remove it from any published Git history if it was pushed. This workspace has no commit history to inspect.
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
- The per-process desktop token restricts unrelated local clients; it does not protect against malicious code running as the same Windows user or a compromised desktop webview.

### Remote backend (opt-in)

Remote API mode is disabled by default. If it is enabled:

- Configure a high-entropy `BLACKMARKET_API_TOKEN`.
- Bind only to the host/interface required by the deployment.
- Use HTTPS/TLS at the ingress and restrict backend ingress to the website/service where possible.
- Do not put the bearer token in browser JavaScript, public build variables, client-side storage, or logs.
- Review `BLACKMARKET_ALLOWED_ORIGINS` and the host's network controls before deployment.

### Website private preview

The website uses a single-password login gate, signed server-side sessions, HttpOnly cookies, same-origin checks for state-changing requests, and a server-side backend proxy. It is **not** a multi-user identity or role-based access system.

The session secret, preview password, backend URL, and backend bearer token must be configured as server-side environment variables. Use a strong unique password and rotate the session secret/password/token if exposed.

## Rate limiting limitations

API, WebSocket, login, and proxy rate limits are implemented as process-local in-memory controls. They reset when the process restarts and are not shared between multiple backend instances. For a multi-instance or public remote deployment, configure an upstream gateway or shared rate limiter; do not rely on process-local counters as distributed abuse protection.

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
- Website hosting/backend services when the private-preview website is configured.

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
| Website session theft | Signed session, HttpOnly/Secure cookie settings, same-origin checks | Single-password preview; not enterprise identity or MFA |
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
- [ ] Verify website secrets are server-only and the preview password is strong.
- [ ] Verify origin/session checks and login throttling with tests.
- [ ] Run dependency and secret scans; review results rather than treating “no findings” as proof.
- [ ] Verify database integrity, backup creation, and restore on a disposable copy.
- [ ] Verify the Windows installer starts and shuts down correctly on a clean Windows environment.
- [ ] Verify artifact version, hash, release notes, signing status, and upgrade/uninstall behavior.
- [ ] Confirm the public website/backend is not advertised as production-ready unless all hosted E2E checks pass.

## Incident response

If a secret is exposed:
1. Revoke or rotate it immediately (Telegram token via BotFather; website/session/backend secrets in the hosting environment).
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


## Stage 3 hosted authentication hardening

The private-preview login now requires a server-side scrypt password hash (`BLACKMARKET_WEB_PASSWORD_HASH`); plaintext `BLACKMARKET_WEB_PASSWORD` is no longer accepted by the updated login code. Password hashing uses Node's built-in scrypt with a random salt and fixed reviewed parameters. The session secret must contain at least 32 bytes.

Hosted session cookies are signed, HttpOnly, SameSite=Strict, Secure in production, host-only, and expire after 30 minutes. Logout revokes the session in the current Node process and clears the cookie. Session revocation state is bounded and process-local; it is not a durable/shared revocation store. Rotating the session secret invalidates all outstanding sessions.

Hosted login and proxy requests reject cross-origin state-changing requests. Login bodies are capped at 8 KiB; proxied mutation bodies are capped at 1 MiB; non-stream backend responses are capped at 2 MiB. Upstream requests have a 15-second timeout. Upstream 5xx response bodies are not forwarded to the browser. Rate-limit identity uses the nearest proxy-provided client address where available, and the in-memory limiter is bounded to avoid unbounded key growth.

### Explicit hosted limitations

- The website remains a **single shared-password private preview**, not multi-user authentication. It has no per-user identity, roles, or authorization ownership model.
- Hosted paper-trading data is currently shared by the configured backend instance. User-owned portfolio, positions, trade history, settings, strategies, and workspaces are not isolated by account. Do not expose the hosted preview as a multi-user service or store multiple users' private data there.
- Session revocation and rate limits are process-local. Multi-instance/serverless deployments need shared persistent session/revocation and rate-limit storage or a suitable upstream identity/gateway.
- The hosted backend must use HTTPS, a high-entropy server-only API token, restrictive ingress, and durable protected storage. A public health endpoint reveals only service readiness, not authentication material.
- Desktop local bearer-token and WebSocket authentication remain separate and unchanged by the website password/session implementation.
