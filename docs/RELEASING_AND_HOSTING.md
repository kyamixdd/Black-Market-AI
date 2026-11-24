# Desktop Release and Hosted Deployment

## Current audit status

Reviewed 24 November 2026. The current local Git repository has no commits, and no installer, hosted deployment, production stream, or current-head CI run was verified. The procedures below describe the intended release process; complete and record each acceptance step against a committed source revision before publishing.

## Desktop release build

The product version is authoritative in `blackmarket-desktop/src-tauri/tauri.conf.json`. The backend health response also reports the product version. Desktop npm and Tauri Cargo package metadata are aligned with the product version; `blackmarket-web/package.json` is the hosted frontend package version.

### Build a Windows installer

On a clean Windows build machine with Python 3.12, Node.js 22, and stable Rust/Cargo configured for an MSVC host, Microsoft C++ Build Tools (MSVC and Windows SDK), and WebView2 installed:

```powershell
./scripts/build_windows_installer.ps1
```

The script creates a temporary backend build environment, runs PyInstaller, includes the output as a Tauri resource, builds the shared frontend, and produces the NSIS installer. The build script is configured to bundle the Python backend; however, the previously exercised 1.0.0 x64 NSIS installation depended on the host's project Python environment. Do not treat the current source configuration as a self-contained desktop release until the exact artifact passes the Windows installer smoke test with Python removed from `PATH` on a clean machine.

### CI release artifact

The Windows installer CI job:
1. Builds from the exact GitHub Actions source commit.
2. Installs the NSIS installer silently.
3. Starts the application with Python removed from PATH and checks backend, SQLite, and WebSocket readiness.
4. Verifies the backend shuts down when the desktop app closes.
5. Reinstalls and verifies that the app-data directory is not removed.
6. Runs the uninstaller and verifies the backend process is not left running.
7. Generates `release-manifest.json` and `installer.sha256`.
8. Uploads the installer and metadata as one workflow artifact.

The manifest records product version, installer filename/size, SHA-256, source commit, branch, workflow run, and Authenticode signature status. The CI artifact archive itself also has a GitHub-provided digest. The installer is currently unsigned unless the manifest reports a valid signer; do not treat an unsigned installer as signed.

### Verify an artifact

Download the installer and `installer.sha256` from the same CI artifact. In PowerShell:

```powershell
Get-FileHash .\\BlackMarket*setup.exe -Algorithm SHA256
Get-Content .\\installer.sha256
Get-Content .\\release-manifest.json
```

Confirm the computed SHA-256, filename, product version, and `sourceCommit` match the manifest and the workflow run. Do not publish a different rebuilt installer under the same release entry.

### Version update

Before preparing a new release, update the product version in Tauri configuration and the backend health version, then keep the desktop npm/Cargo package versions aligned. Update the hosted web package version if the hosted release is being versioned at the same time. Rebuild and verify the lockfiles; do not hand-edit dependency versions.

## Hosted architecture and environment

The hosted Next.js app is configured for a server-side backend proxy. Keep `BLACKMARKET_BACKEND_URL`, `BLACKMARKET_API_TOKEN`, `BLACKMARKET_SESSION_SECRET`, and `BLACKMARKET_WEB_PASSWORD_HASH` server-only. Never use a `NEXT_PUBLIC_` prefix for these values.

Set the following in the hosted frontend's server environment:

- `BLACKMARKET_BACKEND_URL`: HTTPS base URL of the deployed FastAPI backend, without a trailing slash.
- `BLACKMARKET_API_TOKEN`: strong bearer token, at least 32 bytes, identical to the backend token.
- `BLACKMARKET_SESSION_SECRET`: strong random session secret.
- `BLACKMARKET_WEB_PASSWORD_HASH`: scrypt hash; never the plaintext password.

The backend must run with remote API mode explicitly enabled, a valid bearer token, and a valid remote host binding. Use HTTPS at the ingress, restrict backend ingress to the frontend/proxy where the host supports it, and do not expose the SQLite file or token. Keep the backend health endpoint reachable for the frontend's server-side health probe.

## Persistence and free-host caveat

SQLite is a local file database. A hosted container's writable filesystem may be ephemeral across deploys/restarts. Do not use an ephemeral filesystem for user/account/paper-trading data and claim durable persistence. A persistent disk or durable database is required; confirm that the chosen host and plan provide it without charge before deploying. Never create a paid resource or enable billing as part of this release process.

The previously used Render UI demo was a static site; it is not evidence of a running FastAPI backend. A Vercel frontend deployment alone is not a complete hosted application.

## Hosted smoke test

Run the manual GitHub Actions workflow **Hosted deployment smoke test** after setting the repository secret `BLACKMARKET_API_TOKEN`. Supply the actual backend HTTPS URL and optional frontend URL. It verifies:
- Backend health reports ready, database connected, and WebSocket service running.
- An unauthenticated API request is rejected.
- An authenticated read-only system status request succeeds.
- The SSE endpoint responds with `text/event-stream`.
- If a frontend URL is supplied, its root responds and its `/api/health` proxy reports the backend connected.

This workflow is a smoke test, not a complete production certification. It does not place paper orders or validate durable storage across a host-level restart. Perform a disposable paper-account round-trip and restart/restore test before public release.

## Deployment status

The Vercel integration currently returns no accessible projects or production deployments for this account context. A Render workspace is available, but the Render connector requires explicit workspace selection before listing its services. No hosted backend service has been verified by this release workflow. Keep the website marked private preview until the hosted smoke test passes against the intended deployment and persistence has been verified.
