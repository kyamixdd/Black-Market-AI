# BlackMarket AI Desktop

This directory contains the canonical React + TypeScript dashboard and the Tauri desktop shell.

## Architecture

- React/Vite frontend packaged inside the Tauri desktop application.
- Tauri desktop shell and Rust backend supervisor.
- Local FastAPI/Python market engine.
- Local authenticated API at `127.0.0.1:8765` by default.
- Paper trading only; no real exchange order execution.

## Live diagnostics

Open **Diagnostics** in the desktop navigation to inspect backend supervisor/API/database readiness, event-stream and market-scanner state, recent persisted activity, and backend process output. The log tail is bounded and redacts common credential fields. Rolling 60-second API request count, failures, average duration, and p95 duration are shown without request paths or query values. These indicators describe current observable status; they do not prove every feature is correct or establish live exchange availability.

## Development

Install Node.js/npm and the Tauri development prerequisites (Rust toolchain, MSVC C++ build tools/Windows SDK on Windows, and WebView2).

```bash
npm ci
npm run build
npm run lint
npm test
npm run tauri:dev
```

Vite serves the browser frontend at `http://localhost:3000` and proxies API requests through a server-side local API token; the token is never sent to browser JavaScript. Vite alone does not start the Python backend. Start it with Tauri first so the backend supervisor is running.

On Windows, run `..\START_BLACKMARKET_DEV.bat` from Explorer or PowerShell. It installs locked npm dependencies if needed, runs lint/tests/build, then starts Tauri and its supervised backend. While the launcher is running, open `http://localhost:3000` in a browser to use the same local backend. The browser proxy is loopback-only and uses the token stored in the Tauri app data directory.

If `CHECK_BLACKMARKET.bat` reports HTTP 500, the health check has found an existing but unhealthy backend process (often an older app still running in the notification-area tray). Choose **Quit** from the old BlackMarket AI tray menu, then run the development launcher again. The current backend log is `%APPDATA%\com.blackmarket.ai\logs\backend.log`.

## Windows installer

From the repository root, run:

```powershell
./scripts/build_windows_installer.ps1
```

The script builds the bundled Python backend, then builds the Tauri NSIS installer. Output is under `src-tauri/target/release/bundle/nsis`.

The repository contains a Windows installer smoke-test workflow. A current-source local 1.0.0 artifact was built, but it is unsigned (`NotSigned`) and has not passed clean-machine installer acceptance. A valid code-signing certificate and signing tool were not present in the environment during this implementation. Do not distribute the artifact as signed. Release acceptance includes clean-machine readiness/shutdown, upgrade/data-retention, uninstall, signature, and manifest checks.

## Release caveat

Frontend and CI results do not establish live exchange availability, desktop installer readiness, or future model/trading performance. See [release readiness](../docs/RELEASE_READINESS.md).
