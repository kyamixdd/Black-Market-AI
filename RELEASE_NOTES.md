# BlackMarket AI 1.0.0 — Beta Release Candidate

> Status refreshed 23 November 2026. Source audit baseline: `49e6841215303ed296ced4fc1ef3039b9959426d`. This note is not evidence of a new binary, deployment or current-head CI pass.

> Documentation status refreshed 23 November 2026. The comprehensive source audit reviewed application baseline `49e6841215303ed296ced4fc1ef3039b9959426d`. This note is not evidence of a new binary, deployment, or current-head CI pass.

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
