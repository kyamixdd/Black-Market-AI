# Desktop Release Procedures

## Current audit status

Reviewed 25 November 2026 at baseline commit `466dbc7` with uncommitted changes. A current-source 1.0.0 x64 NSIS installer was rebuilt locally after fixing missing SciPy and XGBoost contents in the frozen backend: 110,937,164 bytes, SHA-256 `c29e932e2efe8bfa793f2c5a4c0eb1a959cfdd7acb87232d97f8791c826f8d89`, Authenticode `NotSigned`, source `local-uncommitted`. Its bundled backend passed import and readiness/shutdown smoke tests with Python absent from `PATH`; the exact installer has not undergone install/upgrade/uninstall acceptance. Production stream testing and current-head CI remain unverified. Complete and record each acceptance step against a reviewed source revision before publishing.

## Desktop release build

The product version is authoritative in `blackmarket-desktop/src-tauri/tauri.conf.json`. The backend health response also reports the product version. Desktop npm and Tauri Cargo package metadata are aligned with the product version.

### Build a Windows installer

On a clean Windows build machine with Python 3.12, Node.js 22, and stable Rust/Cargo configured for an MSVC host, Microsoft C++ Build Tools (MSVC and Windows SDK), and WebView2 installed:

```powershell
./scripts/build_windows_installer.ps1
```

The script creates a temporary backend build environment, runs PyInstaller, includes the output as a Tauri resource, builds the shared frontend, and produces the NSIS installer. The backend build collects SciPy's dynamic `array_api_compat` imports plus XGBoost binaries and package data, then runs the frozen executable with `--check-imports` before copying it into the app. A recent diagnostics log exposed missing bundle contents; the rebuilt backend passed both this import check and a temporary-data readiness/shutdown test with `PATH` restricted to Windows system directories. Still do not treat an installer as release-accepted until that exact NSIS artifact passes clean-machine install, readiness, shutdown, and uninstall tests.

For a one-command Windows build from the repository root, run `BUILD_WINDOWS_INSTALLER.bat`. It compiles the backend, runs non-live Python tests, installs the locked desktop dependencies, runs desktop tests and lint, verifies product versions, builds the frozen backend and NSIS installer, then writes `installer.sha256` and `release-manifest.json` under `release-output`. It requires an existing `.venv` with project test dependencies, Python 3.12 available through the Windows Python Launcher, Node.js/npm, Rust/Cargo with the MSVC toolchain, and the Windows desktop build prerequisites above. The installer is created under `blackmarket-desktop/src-tauri/target/release/bundle/nsis/`; the batch file does not install or sign it.

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

### Sign a Windows installer

The repository does not currently automate Authenticode signing. This environment had no valid code-signing certificate with a private key in the current-user or local-machine certificate store, and no `signtool.exe`; the installer is therefore unsigned. Before a signed release, install a trusted certificate and the Windows SDK signing tool on the release machine. Sign the final NSIS executable, verify `Get-AuthenticodeSignature` reports `Valid` and the expected signer, then run `write_release_manifest.ps1` so the hash describes the signed bytes. Signing after manifest generation invalidates its checksum. Never put a PFX password, private key, or certificate secret in repository files or build logs.

### Verify an artifact

Download the installer and `installer.sha256` from the same CI artifact. In PowerShell:

```powershell
Get-FileHash .\\BlackMarket*setup.exe -Algorithm SHA256
Get-Content .\\installer.sha256
Get-Content .\\release-manifest.json
```

Confirm the computed SHA-256, filename, product version, and `sourceCommit` match the manifest and the workflow run. Do not publish a different rebuilt installer under the same release entry.

### Version update

Before preparing a new release, update the product version in Tauri configuration and the backend health version, then keep the desktop npm/Cargo package versions aligned. Rebuild and verify the lockfiles; do not hand-edit dependency versions.

## Production scope

The Tauri desktop installer is the only application target. The Next.js web application and its hosted deployment configuration have been removed. The React/Vite frontend is built as the desktop application's embedded UI and is not a separately deployable web application.
