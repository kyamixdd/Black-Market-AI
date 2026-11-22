# Release Readiness

## Audit metadata

- Review date: 2026-11-22
- Repository: `kyamixdd/Black-Market-AI`
- Branch: `black-market-ai-beta`
- Product version: `1.0.0` (Tauri configuration and backend health version)
- Latest successful full CI evidence before Stage 12 release-workflow changes: run #517 / workflow run ID `45042936231`
- Verified source commit for that artifact: `15004ecda6ace15c24747dd966557222a27a026d`

## Release classification

**Desktop: beta / release candidate. Hosted website: private preview, not production-ready.**

This is an evidence-based engineering readiness assessment, not a security certification or financial performance rating. A green frontend build does not prove the hosted backend, account persistence, or streaming behavior works in production.

## Desktop release evidence

GitHub Actions run `45042936231` completed successfully. It built the Windows self-contained backend and NSIS installer and performed an automated install/startup/shutdown/uninstall smoke test.

Evidence from that run:
- PyInstaller bundled backend: approximately 352.7 MB.
- NSIS installer: approximately 143.37 MiB.
- Installed app started with Python removed from PATH.
- Health check verified backend readiness, SQLite connectivity, and WebSocket readiness.
- Desktop shutdown terminated the backend process.
- Silent uninstall completed without leaving the backend process running.
- GitHub artifact archive digest: `sha256:8c56c4ee485c06b3461a82bf0f94b00dadd4c9e2beb9b4f3c9ffafd0807ac8bc`.
- Artifact source commit: `15004ecda6ace15c24747dd966557222a27a026d`.

This artifact predates the Stage 12 version-alignment, manifest, and tagged-release automation commits. Do not publish it as the tested artifact for a later source revision. The updated branch CI must complete successfully before selecting its artifact for release.

## Stage 12 release improvements

- Desktop npm package, Tauri Cargo package, Cargo lock entry, and desktop npm lock root are aligned to product version `1.0.0`.
- Added `scripts/verify_release_version.py` to check Tauri, backend health, desktop package/lock, Cargo package/lock, and hosted package versions.
- Added `scripts/write_release_manifest.ps1` to validate installer filename/version and write installer SHA-256 and source/run/signature metadata.
- Windows CI now uploads the installer with `release-manifest.json` and `installer.sha256`.
- Windows CI checks reinstall preservation of a marker in the user data directory.
- Added a tag-triggered release workflow. A matching `vX.Y.Z` tag builds and tests the installer, then creates a **draft** GitHub release using the same tested installer and its metadata. Draft releases require review before publication.
- Added `RELEASE_NOTES.md` and `docs/RELEASING_AND_HOSTING.md`.

## Desktop checks still required before public release

- [ ] Complete a clean-machine manual acceptance test on supported Windows versions.
- [ ] Verify an actual version-to-version upgrade, not only same-version reinstall.
- [ ] Verify uninstall behavior with real user data and confirm whether data should be retained or removed.
- [ ] Review installer signing. The installer is not signed unless the release manifest reports a valid Authenticode signer.
- [ ] Verify release tag, release notes, manifest, installer filename/version, source commit, and checksum all match.
- [ ] Confirm the final published installer is the exact tested installer; do not rebuild after testing and publish a different binary.

## Hosted deployment status

**No complete hosted deployment is verified.**

- The current Vercel connector context returned no accessible projects or production deployments for this repository.
- Previous Vercel setup records described a Next.js root directory under `blackmarket-web`, but the Git integration/deployment was not confirmed against the current branch and source.
- The previously used Render UI demo was a static site, not a verified FastAPI backend.
- A Render workspace is available, but service inventory could not be queried without explicit workspace selection in the current connector session.
- No current hosted FastAPI backend URL, durable database, server-side token configuration, or end-to-end deployment has been verified.

The hosted frontend expects server-only `BLACKMARKET_BACKEND_URL`, `BLACKMARKET_API_TOKEN`, `BLACKMARKET_SESSION_SECRET`, and `BLACKMARKET_WEB_PASSWORD_HASH`. These must not be exposed as client-side variables. The backend must use remote API mode, a strong bearer token, HTTPS ingress, and restricted network access where supported.

The new manual **Hosted deployment smoke test** checks backend health/database/WebSocket status, rejects unauthenticated API requests, accepts authenticated read-only status requests, checks SSE headers/initial data, and optionally checks the frontend's server-side `/api/health` proxy. It has not been run against a verified deployment because no intended backend/frontend URLs were available from the connected deployment accounts.

## Hosted persistence and $0 constraint

The project must remain on a strict free deployment path. Do not enable billing or create paid resources.

SQLite persistence is only durable when the database file is stored on durable storage. A free hosted container's ephemeral filesystem must not be treated as durable account, paper-trading, or strategy data. Verify durable storage and restart/restore behavior for the chosen host before enabling hosted paper accounts.

## Release decision

The desktop remains a **beta / release candidate**. The successful Windows smoke test establishes a useful packaging baseline, but Stage 12 release automation changes require a fresh successful CI run and its artifact must be traced by manifest/checksum.

The hosted web application remains **private preview** until a real backend is connected, server-side secrets/authentication are verified, API/SSE connectivity succeeds, and database persistence survives a host restart and restore test.

No real-money execution is supported or intended. Market data, simulated fills, backtests, and model outputs are not guaranteed financial outcomes.

## References

- [Repository](https://github.com/kyamixdd/Black-Market-AI)
- [Working branch](https://github.com/kyamixdd/Black-Market-AI/tree/black-market-ai-beta)
- [Latest CI run used for packaging evidence](https://github.com/kyamixdd/Black-Market-AI/actions/runs/45042936231)
- [Desktop release workflow](.github/workflows/desktop-release.yml)
- [Hosted smoke workflow](.github/workflows/hosted-smoke.yml)
- [Release and hosting guide](docs/RELEASING_AND_HOSTING.md)
- [Security policy](SECURITY.md)
