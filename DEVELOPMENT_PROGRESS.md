# Development Status

## Current baseline

- Branch: `black-market-ai-beta`
- Source baseline reviewed: `49e6841215303ed296ced4fc1ef3039b9959426d`
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

- Root `LICENSE` is present and identifies the project as proprietary; confirm distribution rights and EULA before release.
- Complete manual Windows clean-install, upgrade and uninstall acceptance.
- Verify signing status and exact release artifact metadata/checksum.
- Complete hosted backend and persistence verification before public website access.
- Finish release security review, reconcile documentation, inspect tracked `.db.gz` backups, and verify the exact release candidate.

Detailed release gates are maintained in [RELEASE_READINESS.md](RELEASE_READINESS.md).

## Current repository status — 23 November 2026

This document is maintained against the `black-market-ai-beta` branch. The latest application-source baseline reviewed for the comprehensive product audit is `49e6841215303ed296ced4fc1ef3039b9959426d`. Subsequent commits in this branch update documentation only; verify the branch head before treating this snapshot as current runtime or CI evidence.

Current product classification: **Windows desktop beta candidate; hosted website private preview**. The application is local-first market research and paper-trading software. Paper trading is the only execution mode; no real-money exchange order execution is supported or verified. The deterministic assistant is read-only by default; an optional OpenAI-compatible endpoint may provide interpretation. ML training and model registration do not establish profitability or promotion without the configured validation evidence.

Current audit corrections and outstanding items:
- A root `LICENSE` file exists and identifies the project as proprietary. Older statements that the root license is absent are stale.
- Existing CI run #605 passed for an earlier source commit, not the current source baseline. Fresh current-head CI and release-artifact verification remain required.
- The website is a private preview with a shared-password session gate, not a multi-user SaaS identity and isolation system. Hosted backend, durable storage, streaming and restore acceptance remain release gates.
- The repository tree contains 30 generated compressed shutdown database backups under `data/backups/` with the `.db.gz` suffix. The current ignore rules do not exclude that suffix. Their contents were not inspected in this audit; review them safely and remove generated database artifacts from version control after confirming data-handling requirements.
- The application does not encrypt SQLite databases, model artifacts or backup archives. SHA-256 manifests provide integrity checking, not confidentiality.

This status block records source/documentation evidence only. It does not claim a live deployment test, fresh training run, new backtest, current-head CI pass, security certification or trading performance result.
