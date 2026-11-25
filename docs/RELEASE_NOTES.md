# Unreleased — Audit and release hardening

This note records source/documentation changes only. No installer or hosted deployment was produced during this audit. A previously built 1.0.0 x64 NSIS artifact was exercised for install, readiness, loopback authentication, duplicate launch, and graceful close; it depended on host Python/backend dependencies, and visual/custom-button interaction was not manually verified. The application version remains `1.0.0`.

## Changes in this workspace

- Removed the non-placeholder Telegram token and chat ID from `.env.example`; Telegram is disabled in the template.
- Removed unused Binance API key/secret configuration. Public market-data access does not require exchange credentials.
- Reject `REAL_TRADING_ENABLED=true` during startup configuration validation. Paper trading remains the only execution mode.
- Reject malformed explicit boolean/numeric settings and unsupported non-SQLite database URLs during configuration validation.
- Added a regression test for rejecting real-trading configuration.
- Registered the `live` pytest marker and selected the async fixture loop scope.
- Reconciled current project, security, and release status documentation and updated `docs/LOCAL_AUDIT_REPORT.md`.

## Release status

Public release remains blocked. Revoke the exposed Telegram token, resolve adaptive-risk evidence limitations, establish a reviewed source commit, rerun CI, and complete desktop installer, backup/restore, dependency, security, and legal acceptance. Review tracked local data/build outputs before publication. See `RELEASE_READINESS.md` and `docs/PROJECT_STATUS.md`.
