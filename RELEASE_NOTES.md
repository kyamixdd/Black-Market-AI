# BlackMarket AI 1.0.0 — Beta Release Candidate

## Included

- Shared React/TypeScript market research dashboard for desktop and hosted web.
- Tauri desktop application with a bundled self-contained Python backend.
- Local SQLite persistence, backup and recovery support.
- Market data, scanner, indicators, strategy research, backtesting and model evaluation.
- Paper-only order and position management with risk controls.
- Server-side hosted authentication and backend proxy architecture.
- Automated frontend/backend regression, responsive browser, and Windows installer checks.

## Installation and verification

Use the Windows NSIS installer attached to the draft GitHub release. Verify its SHA-256 against `installer.sha256` and inspect `release-manifest.json` for source commit, version and signature status.

## Important limitations

- This is a beta/release candidate, not a security certification or financial product.
- Paper trading only; no real-money execution.
- Market data depends on exchange/network availability.
- Installer signing is not enabled by default; check the manifest signature status.
- Hosted website remains private preview until backend authentication, durable persistence, SSE and hosted health smoke tests pass.
- Do not use an ephemeral hosted filesystem for persistent SQLite account or paper-trading data.
