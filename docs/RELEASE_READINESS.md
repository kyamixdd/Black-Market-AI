# Release Readiness

## Snapshot

- Review date: 2026-11-24
- Workspace: local source tree; no commits exist in its Git repository.
- Source identity: not established. All application files are uncommitted.
- Product version: `1.0.0`

## Release classification

**Public release: blocked. Desktop: beta candidate. Website: private preview.**

The desktop frontend and local Python tests/builds passed in this workspace. The Tauri installer, Windows installation/upgrade/uninstall flow, release signing, production market streams, and hosted services were not exercised in this audit. This document is release acceptance evidence, not a security certification or financial performance assessment.

## Local verification

- Python regression suite: 669 passed, 3 live tests deselected on Python 3.13; Python 3.12 was not run locally.
- Desktop frontend: production build passed; 16 service tests passed; lint completed with warnings.
- Responsive browser smoke passed at eight widths, checking overflow, primary navigation, chart-settings interaction, and page errors; this does not replace full desktop UI acceptance.
- Website: production build and TypeScript check passed; 8 session/rate-limit security tests passed; `npm ci` and `npm audit --audit-level=high` reported zero vulnerabilities.
- Python `pip-audit -r src_tauri/backend/requirements.txt` reported no known vulnerabilities; `pip check` reported no broken requirements.
- A Python wheel built and installed into an isolated target; backend package imports passed from a clean working directory on Python 3.13. Python 3.12 CI verification remains pending.
- Website build completed without the earlier Windows SWC fallback warning. The desktop build still reports a 560.79 kB main chunk; desktop lint reports existing warnings.
- No Tauri/NSIS installer build, full browser/device acceptance, hosted smoke test, production stream test, backup restore, or current-head CI run was performed.
- The repository has no source commit to associate with these results. Run CI after committing the release candidate.

## Desktop release checks

The repository contains a Windows installer workflow. Its claims and the installer itself were not validated in this workspace.

Complete before public release:

- [ ] Revoke the Telegram token previously present in `.env.example`; confirm its absence from external history and release artifacts. A local scan found no Telegram-token-shaped value in this workspace.
- [ ] Establish a clean source commit and run CI against that exact commit.
- [x] Replace fabricated adaptive drawdown and correlation metrics; incomplete evidence is reported as unavailable. The main simulator does not currently supply all evidence to this assessment.
- [x] Run local Python and website dependency audits; both reported no known vulnerabilities. Repeat against the committed release source.
- [x] Add `blackmarket-web/package-lock.json`, use `npm ci` in CI, and verify `npm audit --audit-level=high` locally.
- [ ] Run secret scans against the committed source and built release artifacts.
- [x] Run responsive browser smoke at eight viewports, including overflow,
  primary navigation, chart-settings interaction, and page errors.
- [ ] Complete full-screen, keyboard, and manual Tauri interaction acceptance.
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

Review [SECURITY.md](../SECURITY.md) for the threat model. The local API is loopback-bound by default with bearer authentication; remote mode is opt-in. Production Tauri CSP excludes development-server origins. SQLite and backup archives are not application-encrypted. Hosted process-local rate/session controls are not distributed abuse protection.

Before publication, repeat dependency and secret scans on the committed source and release artifact, review GitHub Actions permissions, and inspect the artifact and source commit.

## Release decision

Do not publish a release artifact from this uncommitted workspace. Resolve external token revocation/history checks, source provenance and desktop acceptance items first. Keep the website private preview until identity isolation, hosted backend, production streaming, durable storage, rate limiting, backup/restore and deployment checks are complete.

Paper trading, market signals, backtests and model outputs are research tools. No real-money execution is supported or intended, and no result guarantees future profitability.

## References

- [Repository](https://github.com/kyamixdd/Black-Market-AI)
- [Release and hosting procedures](RELEASING_AND_HOSTING.md)
