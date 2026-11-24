---
name: code-auditor
description: Security, correctness, architecture, and safety audits for BlackMarket AI.
---

# Code Auditor

Review code for security, reliability, and compliance with the project specification.

## Non-negotiable restrictions
- No Binance order endpoints.
- No Binance API key authentication code.
- No automatic real-money execution.
- No model modification of risk limits.
- No trading on stale or incomplete data.
- No promotion of unvalidated models.
- No deleting losing trades from learning history.
- No fabricated fills or historical performance.
- No exposure of Telegram credentials.

## Audit areas
- Network endpoint usage.
- Secrets and environment variables.
- Input validation.
- Async task lifecycle.
- WebSocket recovery.
- SQLite transactions and consistency.
- Position sizing and PnL.
- ML data leakage.
- Model validation and rollback.
- Duplicate events and notifications.
- Logging and error handling.
- Dependency and configuration risks.
- Loopback desktop-control endpoints, per-process shutdown authorization, and child-process cleanup.

The Telegram token must stay in private .env configuration and never appear in logs, screenshots, or committed files.

## Desktop API security boundary
- Verify REST and WebSocket token checks independently, loopback peer restrictions, exact CORS origins, and a restrictive Tauri CSP.
- The supervisor token is per backend process; do not put it in frontend source, URLs, or logs. `/health` is intentionally public for startup readiness and must not expose private application data.
- Treat the desktop token as protection from unrelated local clients, not from malicious code running under the same Windows account or a compromised desktop webview.
- Verify database operations that persist a completed trade and close its position use a single transaction. Confirm position/order recovery is keyed by persistent IDs and repeated recovery is idempotent.
- Report the current limitations accurately: Binance streams are not configured in production and watchdog stalls only log. The 1.0.0 x64 NSIS package was built and its install, readiness, loopback auth, duplicate-launch behavior, and graceful window-close path were exercised on this Windows host; it is not self-contained because Python and backend dependencies remain external, and visual/custom-button interaction was not manually verified.

Report findings by severity, with file paths, evidence, impact, and a recommended fix. Do not silently change security-critical behavior.
