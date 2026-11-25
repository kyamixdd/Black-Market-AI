# Release Readiness

## Snapshot

- Review date: 2026-11-25
- Workspace: local source tree on branch `Black-Market-AI-Beta-1.0.1`; baseline commit `466dbc7` with uncommitted changes.
- Source identity: baseline commit recorded; this working-tree state is not committed or release-verified.
- Product version: `1.0.0`

## Release classification

**Public release: blocked. Desktop: beta candidate. Web production: unsupported and removed from the release path.**

The desktop frontend and local Python tests/builds passed in this workspace. The packaged backend was rebuilt after diagnostics exposed missing SciPy and XGBoost files in the prior PyInstaller bundle. Its frozen import check passed, and the executable reached backend/database/WebSocket readiness and shut down cleanly using isolated data with Python absent from `PATH`. The refreshed 1.0.0 x64 NSIS installer was built, but installation/upgrade acceptance of that exact installer was not run. It is unsigned; no valid code-signing certificate or `signtool.exe` was available locally. Production market streams and visual/custom-button interaction remain unverified. This document is release acceptance evidence, not a security certification or financial performance assessment.

## Local verification

- Python regression suite: 670 passed, 3 live tests deselected on Python 3.13; Python 3.12 was not run locally.
- Desktop frontend: production build passed; 17 service tests passed; lint completed without reported issues.
- Tauri supervisor: 5 Rust tests passed, including log-tail bounds and sensitive-entry redaction.
- Packaged backend: PyInstaller `--check-imports` passed with SciPy `array_api_compat` submodules and XGBoost binaries/data collected. The executable became ready with SQLite and WebSocket on a temporary port, then shut down gracefully using a temporary data directory and `PATH` restricted to Windows system locations.
- Current-source Windows installer: 110,937,164 bytes; SHA-256 `c29e932e2efe8bfa793f2c5a4c0eb1a959cfdd7acb87232d97f8791c826f8d89`; manifest checksum matches; Authenticode status `NotSigned`; source identity `local-uncommitted`.
- Responsive browser smoke passed at eight widths, checking overflow, primary navigation, chart-settings interaction, and page errors; this does not replace full desktop UI acceptance.
- Python `pip-audit -r src_tauri/backend/requirements.txt` reported no known vulnerabilities; `pip check` reported no broken requirements.
- A Python wheel built and installed into an isolated target; backend package imports passed from a clean working directory on Python 3.13. Python 3.12 CI verification remains pending.
- The legacy Next.js source is not built by CI and has no production build/start scripts or hosted deployment workflow. The source remains in the dirty working tree and is not part of desktop packaging.
- No install/upgrade/uninstall acceptance of the refreshed installer, full browser/device acceptance, production stream test, backup restore, or current-head CI run was performed. An existing app installation and shared app-data directory were left untouched.
- These results are from an uncommitted working tree based on `466dbc7`. Run CI after committing the release candidate.

## Desktop release checks

The repository contains a Windows installer workflow. Validate the exact release artifact, especially that it runs without host Python or separately installed backend dependencies.

Complete before public release:

- [ ] Revoke the Telegram token previously present in `.env.example`; confirm its absence from external history and release artifacts. The current workspace has no token-shaped value, but a targeted local history scan found one in commit `0415b531e14efa7e03c932a6c1e7ee8492105179`.
- [ ] Establish a clean source commit and run CI against that exact commit.
- [x] Replace fabricated adaptive drawdown and correlation metrics; incomplete evidence is reported as unavailable. The main simulator does not currently supply all evidence to this assessment.
- [x] Run local Python and desktop dependency audits; repeat against the committed release source.
- [ ] Run secret scans against the committed source and built release artifacts.
- [x] Run responsive browser smoke at eight viewports, including overflow,
  primary navigation, chart-settings interaction, and page errors.
- [ ] Complete full-screen, keyboard, and manual Tauri interaction acceptance.
- [ ] Manual clean-machine acceptance of the exact current installer on supported Windows versions, with Python removed from `PATH`.
- [x] Build the current-source Windows NSIS installer and verify its generated SHA-256 manifest.
- [x] Verify the packaged backend imports and reaches readiness/shuts down with Python absent from `PATH` and isolated app data.
- [ ] Version-to-version upgrade test.
- [ ] User-data retention/removal behavior documented and verified.
- [x] Installer Authenticode status checked; disclose unsigned builds. Current artifact is `NotSigned`.
- [ ] Obtain/install a trusted code-signing certificate and signing tool, sign the exact accepted installer, then regenerate and verify the checksum manifest.
- [ ] Release version and notes match the built artifact.
- [ ] Manifest source commit, workflow run, filename, size and SHA-256 match the artifact.
- [ ] Publish the exact tested installer; do not rebuild a different binary after acceptance.
- [ ] Review and safely remove tracked local databases, backups, and generated web build output from version control before publication.
- [x] Confirm root project license exists; it is proprietary. Verify EULA and distribution terms before release.

The root `LICENSE` file exists and identifies the project as proprietary. Public distribution still requires correct license/EULA presentation and third-party license review.

## Security and data

Review [SECURITY.md](../SECURITY.md) for the threat model. The local API is loopback-bound by default with bearer authentication; remote mode is opt-in. Production Tauri CSP excludes development-server origins. SQLite and backup archives are not application-encrypted. API and WebSocket rate controls are process-local.

Before publication, repeat dependency and secret scans on the committed source and release artifact, review GitHub Actions permissions, and inspect the artifact and source commit.

## Release decision

Do not publish a release artifact from this uncommitted workspace. Resolve external token revocation/history checks, source provenance and desktop acceptance items first. Do not treat the retained legacy Next.js source as a supported or deployable production product.

Paper trading, market signals, backtests and model outputs are research tools. No real-money execution is supported or intended, and no result guarantees future profitability.

## References

- [Repository](https://github.com/kyamixdd/Black-Market-AI)
- [Desktop release procedures](RELEASING_AND_HOSTING.md)
