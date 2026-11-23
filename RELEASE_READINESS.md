# Release Readiness

## Snapshot

- Review date: 2026-11-23
- Repository: `kyamixdd/Black-Market-AI`
- Branch: `black-market-ai-beta`
- Reviewed application-source baseline: `49e6841215303ed296ced4fc1ef3039b9959426d`
- Documentation snapshot: prior readiness notes are historical; current documentation updates follow the comprehensive audit of source baseline `49e6841215303ed296ced4fc1ef3039b9959426d`.
- Product version: `1.0.0`

## Release classification

**Desktop: beta candidate. Website: private preview.**

The desktop path has automated packaging and installation smoke-test coverage. The website is not verified as a complete public hosted service. This document records release evidence and outstanding acceptance checks; it is not a security certification or financial performance assessment.

## CI verification

GitHub Actions run [#605](https://github.com/kyamixdd/Black-Market-AI/actions/runs/45055409152) completed successfully for source commit `ee602590442d9d29060d525e1aff5539dc42f01c`.

Successful jobs:

- Responsive browser smoke tests
- Python backend regression tests
- Dependency vulnerability audit
- Desktop TypeScript, lint and market-data tests
- Shared website frontend build
- Rust and Tauri compile checks
- Windows bundled backend and NSIS install smoke test

The result is specific to the recorded commit. A new release candidate requires fresh successful CI and artifact identity verification.

## Desktop release checks

The Windows installer workflow builds the Python backend as a bundled executable, packages it with Tauri/NSIS, and verifies installation, backend readiness, shutdown, reinstall data preservation and uninstall process cleanup.

Complete before public release:

- [ ] Manual clean-machine acceptance on supported Windows versions.
- [ ] Version-to-version upgrade test.
- [ ] User-data retention/removal behavior documented and verified.
- [ ] Installer Authenticode status checked; disclose unsigned builds.
- [ ] Release version and notes match the built artifact.
- [ ] Manifest source commit, workflow run, filename, size and SHA-256 match the artifact.
- [ ] Publish the exact tested installer; do not rebuild a different binary after acceptance.
- [x] Confirm root project license exists; it is proprietary. Verify EULA and distribution terms before release.

The root `LICENSE` file exists and identifies the project as proprietary. Public distribution still requires correct license/EULA presentation and third-party license review.

## Website status

The Next.js website uses server-side single-password authentication and a same-origin backend proxy. It remains a private-preview path.

Required configuration is server-side:

- `BLACKMARKET_BACKEND_URL`
- `BLACKMARKET_API_TOKEN`
- `BLACKMARKET_SESSION_SECRET`
- `BLACKMARKET_WEB_PASSWORD_HASH`

Before public access:

- [ ] Deploy a reachable FastAPI backend with remote API mode explicitly enabled.
- [ ] Verify HTTPS ingress and backend access restrictions.
- [ ] Verify session and backend token handling without exposing secrets to client bundles.
- [ ] Run the hosted deployment smoke test against actual backend/frontend URLs.
- [ ] Verify REST, SSE and WebSocket/event behavior.
- [ ] Verify market-data freshness and reconnect behavior.
- [ ] Complete a disposable paper-account order lifecycle.
- [ ] Verify database durability across restart/deploy.
- [ ] Complete backup and restore validation.
- [ ] Document that the current shared-password gate is not multi-user identity or per-user data isolation.

A Vercel frontend build or static deployment does not establish a working hosted Python engine.

## Security and data

Review [SECURITY.md](SECURITY.md) for the threat model. The local API is loopback-bound by default with bearer authentication; remote mode is opt-in. SQLite and backup archives are not application-encrypted. Hosted process-local rate/session controls are not distributed abuse protection.

Before publication, review dependencies and GitHub Actions permissions, confirm no secrets are committed, and inspect the release artifact and source commit.

## Release decision

The desktop can be treated as a beta candidate after the remaining manual acceptance and artifact checks are complete. The website must remain private preview until the hosted backend, authentication, streaming, durable storage and restore workflow have been verified.

Paper trading, market signals, backtests and model outputs are research tools. No real-money execution is supported or intended, and no result guarantees future profitability.

## References

- [Repository](https://github.com/kyamixdd/Black-Market-AI)
- [Working branch](https://github.com/kyamixdd/Black-Market-AI/tree/black-market-ai-beta)
- [Reviewed source commit](https://github.com/kyamixdd/Black-Market-AI/commit/ee602590442d9d29060d525e1aff5539dc42f01c)
- [CI run #605](https://github.com/kyamixdd/Black-Market-AI/actions/runs/45055409152)
- [Release and hosting procedures](docs/RELEASING_AND_HOSTING.md)


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
