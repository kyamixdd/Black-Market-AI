# Project Status

## Snapshot

- Branch: `black-market-ai-beta`
- Reviewed source commit: `49e6841215303ed296ced4fc1ef3039b9959426d`
- Documentation snapshot: `c9e488f14814b670308574582c6e7cb175c2b51b`
- Product version: `1.0.0`
- Classification: desktop beta candidate; website private preview
- Latest reviewed CI: [run #605](https://github.com/kyamixdd/Black-Market-AI/actions/runs/45055409152), successful

## Engineering assessment

Overall score: **7.6 / 10 — advanced beta, not public-release ready**

The score weights implementation completeness, correctness evidence, security, operability and release readiness. UI appearance is not used as a substitute for working backend behavior. This is a source-and-CI assessment; live hosted operation and profitability are not scored as verified.

| Area | Score |
|---|---:|
| Frontend and shared UI | 8.2/10 |
| Desktop packaging and lifecycle | 8.0/10 |
| Backend/API architecture | 7.8/10 |
| Market data and analytics | 7.5/10 |
| Paper trading and risk | 7.8/10 |
| Strategy research and backtesting | 7.5/10 |
| Learning and model lifecycle | 7.3/10 |
| Persistence and recovery | 8.0/10 |
| Security controls | 7.0/10 |
| CI and automated verification | 8.5/10 |
| Hosted deployment readiness | 4.5/10 |
| Public release readiness | 5.5/10 |

The lower hosted and release scores reflect the private-preview authentication model, unverified live backend/persistence, missing root license, and remaining manual installer acceptance. The overall score is not a financial-performance rating.

## Product paths

### Tauri desktop

The desktop shell supervises a bundled Python backend. The default local API binds to loopback and uses bearer authentication. The Windows installer workflow builds the backend executable and NSIS package, then runs an install/startup/shutdown/uninstall smoke test.

The reviewed CI run passed the Windows installer smoke test. Manual acceptance on supported Windows versions, upgrade testing, signing review and release-artifact verification remain release tasks.

### Website

The Next.js site uses a server-side single-password session and same-origin backend proxy. It is a private-preview path. It does not provide multi-user identity, role-based access, MFA or per-user hosted account isolation.

A complete hosted backend deployment, durable persistence and end-to-end service verification are not established by the reviewed repository evidence. Do not classify the website as a public production service until the hosted smoke test and persistence/recovery checks pass.

## Implemented subsystems

The current source includes:

- Binance public Spot and USDⓈ-M Futures market data.
- Market scanning, candles, technical analysis and freshness reporting.
- Strategy families and Strategy Lab backtesting/comparison.
- Paper Spot and Futures trading with simulated execution costs and risk controls.
- Learning/prediction outcome records, model registry, calibration and promotion gates.
- Market regime analysis, research snapshots, strategy evolution and drift monitoring.
- Trade review, saved workspaces, shareable analysis and community strategy library.
- SQLite persistence, backup/restore and integrity checks.
- Optional Telegram notifications and deterministic market-intelligence assistant.
- React/TypeScript dashboard shared by desktop and website.
- Textual terminal interface.

Feature status is determined by source implementation and tests. A module or screen being present does not establish performance quality, profitability or hosted availability.

## CI evidence

Run #605 completed successfully for the reviewed branch head. Jobs reported successful:

- Responsive browser smoke tests
- Python backend regression tests
- Dependency vulnerability audit
- Desktop TypeScript, lint and market-data tests
- Shared website frontend build
- Rust and Tauri compile checks
- Windows bundled backend and NSIS install smoke test

These results are commit-specific. Re-run CI after subsequent source or documentation changes.

## Public release blockers

1. Select and add a repository license. No root `LICENSE` file was present in the reviewed tree.
2. Complete manual Windows installation, upgrade, uninstall and user-data retention acceptance on supported systems.
3. Confirm installer signing status and disclose unsigned distribution if signing is not configured.
4. Verify release version, source commit, manifest and checksum against the exact artifact selected for publication.
5. Complete the hosted backend deployment and verify authentication, API/SSE connectivity, data freshness, paper-trading workflow and durable storage before making the website public.
6. Run a security review of the exact release candidate and resolve release-blocking findings.
7. Confirm release notes, support scope, privacy/data handling and financial-use disclaimers.

## Known constraints

- Paper trading only; no real exchange order execution.
- Public market data depends on exchange/network availability and rate limits.
- Local SQLite and backup files are not application-encrypted.
- Website login and process-local rate/session controls are private-preview controls, not a multi-user public SaaS security model.
- Model validation and backtest results do not guarantee future profitability.
- A successful CI run is not a live deployment verification or security certification.


## Current repository status — 23 November 2026

Maintained against `black-market-ai-beta`; application-source baseline reviewed: `49e6841215303ed296ced4fc1ef3039b9959426d`. Later commits in this branch are documentation-only at the time of this update. Verify the branch head before relying on this snapshot as current runtime or CI evidence.

**Classification:** Windows desktop beta candidate; hosted website private preview. BlackMarket AI is local-first market research and paper-trading software. Paper trading is the only execution mode; real-money exchange order execution is not supported or verified. The assistant is deterministic and read-only by default; the optional OpenAI-compatible provider only interprets retrieved evidence. ML training or model registration does not establish profitability or promotion without validation evidence.

Audit corrections and outstanding work:
- Root `LICENSE` exists and identifies the project as proprietary. Statements that no root license exists are outdated.
- CI run #605 passed on an earlier commit, not the current source baseline. Fresh current-head CI and release-artifact verification remain required.
- The website is a shared-password private preview, not multi-user identity or tenant isolation. Hosted backend, durable storage, streaming and restore acceptance remain release gates.
- The repository contains 30 generated compressed shutdown database backups under `data/backups/` using `.db.gz`; the current ignore rules do not exclude this suffix. Contents were not inspected. Review safely and remove generated database artifacts from version control.
- SQLite databases, model artifacts and backup archives are not application-encrypted. SHA-256 manifests provide integrity, not confidentiality.

This is source/documentation evidence only; it does not claim live deployment verification, fresh training/backtest, current-head CI, security certification or profitable performance.
