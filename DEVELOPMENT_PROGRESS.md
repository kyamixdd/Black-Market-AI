# Development Status

## Current baseline

- Branch: `black-market-ai-beta`
- Source baseline reviewed: `ee602590442d9d29060d525e1aff5539dc42f01c`
- Product version: `1.0.0`
- Current classification: desktop beta candidate; website private preview

## Application components

The repository contains the shared React/TypeScript dashboard, Tauri desktop shell, supervised Python backend, market-data and analysis services, strategy engine, paper-trading simulator, risk controls, learning/model lifecycle, persistence/recovery, and the Next.js private-preview website.

## Current feature areas

- Public Binance Spot and USDⓈ-M Futures data
- Multi-timeframe market analysis and scanner
- Strategy signals and Strategy Lab
- Simulated Spot/Futures order and position management
- Runtime risk settings and limits
- Prediction outcomes, model registry, calibration and promotion controls
- Market regime, research, drift and strategy-evolution tooling
- Trade review, workspaces and shareable analysis
- Community strategy library
- SQLite persistence and backup/restore
- Optional Telegram notifications
- Deterministic market-intelligence assistant

## Verification

GitHub Actions run [#605](https://github.com/kyamixdd/Black-Market-AI/actions/runs/45055409152) passed for the baseline commit. It covered responsive browser smoke tests, Python regression tests, dependency audit, desktop TypeScript/lint/market-data tests, website build, Rust/Tauri checks and Windows installer smoke tests.

These checks do not replace manual release acceptance or hosted-service verification.

## Release work remaining

- Add a project license before public source distribution.
- Complete manual Windows clean-install, upgrade and uninstall acceptance.
- Verify signing status and exact release artifact metadata/checksum.
- Complete hosted backend and persistence verification before public website access.
- Finish release security review and confirm documentation matches the release candidate.

Detailed release gates are maintained in [RELEASE_READINESS.md](RELEASE_READINESS.md).