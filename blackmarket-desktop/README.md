# BlackMarket AI Desktop

This directory contains the canonical React + TypeScript dashboard and the Tauri desktop shell.

## Architecture

- React/Vite frontend shared with the Next.js website.
- Tauri desktop shell and Rust backend supervisor.
- Local FastAPI/Python market engine.
- Local authenticated API at `127.0.0.1:8765` by default.
- Paper trading only; no real exchange order execution.

## Development

Install Node.js/npm and the Tauri development prerequisites (Rust toolchain, MSVC C++ build tools/Windows SDK on Windows, and WebView2).

```bash
npm ci
npm run build
npm run lint
npm test
npm run tauri:dev
```

The browser-only `npm run dev` / Vite preview does not start the supervised Python backend. Tauri is the supported development path for validating desktop startup and managed backend lifecycle.

## Windows installer

From the repository root, run:

```powershell
./scripts/build_windows_installer.ps1
```

The script builds the bundled Python backend, then builds the Tauri NSIS installer. Output is under `src-tauri/target/release/bundle/nsis`.

The repository CI includes a Windows installer smoke test. Release acceptance includes manual verification of the release artifact/version and a user-data backup before installation or upgrade.

## Website sharing

The Next.js website imports this canonical source tree. The website imports this shared source tree; UI changes belong here. Website server configuration and private-preview limitations are documented in `../blackmarket-web/README.md`.

## Release caveat

Frontend and CI results do not establish live exchange availability, hosted deployment readiness, or future model/trading performance. See the repository root `RELEASE_READINESS.md`.


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
