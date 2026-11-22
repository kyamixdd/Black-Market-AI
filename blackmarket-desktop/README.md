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

The browser-only `npm run dev` / Vite preview does not start the supervised Python backend. Use Tauri to validate desktop startup and backend lifecycle.

## Windows installer

From the repository root, run:

```powershell
./scripts/build_windows_installer.ps1
```

The script builds the bundled Python backend, then builds the Tauri NSIS installer. Output is under `src-tauri/target/release/bundle/nsis`.

The repository CI includes a Windows installer smoke test. Still perform release-specific manual acceptance, verify the exact artifact and version, and back up user data before installing/upgrading.

## Website sharing

The Next.js website imports this canonical source tree. Keep UI changes here rather than maintaining a separate website copy. Website server configuration and private-preview limitations are documented in `../blackmarket-web/README.md`.

## Release caveat

A passing frontend build or CI run does not prove live Binance availability, hosted website/backend readiness, or future ML/trading performance. See the repository root `RELEASE_READINESS.md`.
