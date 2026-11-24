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

The repository contains a Windows installer smoke-test workflow, but that workflow was not verified against this local source tree. Release acceptance includes manual verification of the release artifact/version and a user-data backup before installation or upgrade.

## Website sharing

The Next.js website imports this canonical source tree. The website imports this shared source tree; UI changes belong here. Website server configuration and private-preview limitations are documented in `../blackmarket-web/README.md`.

## Release caveat

Frontend and CI results do not establish live exchange availability, hosted deployment readiness, or future model/trading performance. See the repository root `RELEASE_READINESS.md`.
