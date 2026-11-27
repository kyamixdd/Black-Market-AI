# BlackMarket AI

Local-first cryptocurrency market analysis, strategy research and paper-trading application.

BlackMarket AI combines public Binance market data, technical analysis, strategy evaluation, simulated execution, risk controls and local learning tools. The supported desktop product runs a Tauri shell with a supervised Python backend. Trading is simulated; the application does not submit real exchange orders.

## Current audit state — 25 November 2026

- Product version: `1.0.0`.
- Product classification: Windows desktop beta candidate; desktop is the only supported production target.
- The current branch is `Black-Market-AI-Beta-1.0.1` at local commit `466dbc7`; the working tree contains uncommitted changes. The current-source Windows NSIS installer was built locally, but no remote CI result or clean-machine installer acceptance was verified.
- The local source test/build and installer hash/signature evidence are recorded in [Project Status](docs/PROJECT_STATUS.md). They do not verify production Binance streams, clean-machine installer behavior, financial performance, or security certification.
- A non-placeholder Telegram token was present in `.env.example` during this audit and has been removed. Treat it as compromised and rotate/revoke it before release. See [SECURITY.md](SECURITY.md).
- Public release remains blocked by the open items in [Release Readiness](docs/RELEASE_READINESS.md), including accurate risk-assessment metrics, clean source provenance, and release-artifact verification.

## Capabilities

- Public Binance Spot and USDⓈ-M Futures market data.
- Symbol discovery, market scanning, candle history and multi-timeframe analysis.
- Technical indicators, market breadth, relative strength, volatility and data-freshness reporting.
- Strategy signals and strategy-family evaluation.
- Strategy Lab backtesting and comparison with persisted reports.
- Paper Spot and Futures accounts with simulated fees, spread, slippage, funding, leverage, liquidation and order lifecycle controls.
- Risk limits and runtime risk settings.
- Local learning, prediction outcomes, model registry, calibration and promotion gates.
- Market regime analysis, evidence-linked research, strategy evolution and drift monitoring.
- Trade review, saved workspaces, shareable analysis and community strategy library.
- SQLite persistence, integrity checks, backup/restore and model artifacts.
- Optional Telegram notifications and a deterministic market-intelligence assistant.
- Live desktop diagnostics for subsystem health, persisted activity, bounded backend logs, frontend API/render traces, database-write summaries, and actionable error guidance.
- Textual terminal interface and Tauri desktop interface.

Feature availability depends on configured runtime mode and the data available for the selected asset/timeframe. The application reports unavailable or insufficient data rather than treating it as a valid measurement.

## Application structure

- `blackmarket-desktop/` — shared React/TypeScript dashboard and Tauri desktop shell.
- `blackmarket-web/` — legacy Next.js source retained for reference; no production build, CI, or deployment is supported.
- `src_tauri/backend/` — FastAPI backend, orchestration bridge, market engine and API routes.
- `core/`, `market/`, `exchange/`, `strategies/`, `paper_trading/`, `risk/`, `learning/` — Python engine components.
- `tests/` — backend, frontend-service and subsystem regression tests.
- `.github/workflows/` — backend and desktop CI plus the Windows desktop release workflow.
- `docs/` — product-specific technical and operating documentation.
- `docs/FEATURE_AUDIT.md` — supported desktop/backend feature map and verification boundaries.
- `docs/SYMBOL_CATALOG.md` — generated first-party function-candidate catalog; not a runtime correctness claim.

## Desktop development

Backend development and wheel installation require Python 3.12 or newer, Node.js/npm, and the Tauri platform prerequisites. On Windows, Tauri builds require Rust/Cargo with an MSVC host, Microsoft C++ Build Tools with MSVC and a Windows SDK, and WebView2. Check existing toolchain installations before installing build prerequisites; do not replace a working system Python installation.

Create a Python environment and install the project dependencies:

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
python -m pip install -r src_tauri/backend/requirements.txt
```

The supported Python wheel contains the backend modules and declares their runtime dependencies. It does not include a Python interpreter or replace the desktop installer. The desktop backend build is configured to create a PyInstaller bundle; treat any installer as not self-contained until the exact artifact passes a clean-machine test with Python removed from `PATH`.

Run backend tests:

```bash
python -m pytest -q -m "not live"
```

Run the desktop frontend checks:

```bash
cd blackmarket-desktop
npm ci
npm run build
npm run lint
npm test
npm run tauri:dev
```

The browser-only Vite preview serves the frontend but does not supervise the Python backend. For local browser development, start Tauri with `START_BLACKMARKET_DEV.bat` first, then open `http://localhost:3000`; Vite proxies API requests server-side using the local token without exposing it to browser JavaScript. `npm run tauri:dev` uses a development-only CSP override for Vite HMR; packaged builds use the restrictive production CSP. Use Tauri to verify desktop-managed startup and shutdown.

Build the Windows installer from the repository root:

```powershell
./scripts/build_windows_installer.ps1
```

The installer output is under `blackmarket-desktop/src-tauri/target/release/bundle/nsis/`.

## Security and data

The desktop API binds to loopback by default and requires bearer authentication. Remote API mode is disabled by default. Do not expose the backend directly to the internet without the remote deployment controls described in [SECURITY.md](SECURITY.md).

SQLite databases, model artifacts and backup archives are not application-encrypted. Protect local data using OS-level encryption and access controls. See [Backup and Recovery](docs/BACKUP_GUIDE.md).

## License and distribution

BlackMarket AI is proprietary software. All rights reserved. No permission is granted to copy, modify, redistribute, sublicense, or create derivative or competing products from this source code without prior written permission. See [LICENSE](LICENSE).

The public GitHub repository is source-visible; repository access is not a commercial software license. The commercial product is intended to be distributed as an application, subject to a separate end-user license agreement (EULA). Third-party components remain subject to their own licenses.

Public release also requires the acceptance items in [Release Readiness](docs/RELEASE_READINESS.md), including committed source provenance, Windows upgrade/uninstall checks, signing status disclosure, security review and exact release artifact verification.

## Documentation

- [Release readiness](docs/RELEASE_READINESS.md)
- [Security policy and threat model](SECURITY.md)
- [Backup and recovery](docs/BACKUP_GUIDE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Release and hosting procedures](docs/RELEASING_AND_HOSTING.md)
- [Project status and audit](docs/PROJECT_STATUS.md)
- [Feature and implementation audit](docs/FEATURE_AUDIT.md)
- [Generated symbol catalog](docs/SYMBOL_CATALOG.md)
- [Market-intelligence assistant](docs/assistant-intelligence.md)
- [Community strategy library](docs/COMMUNITY_STRATEGY_LIBRARY.md)
- [Complete product, architecture, feature and operating guide](docs/blackmarketai.md)

## Disclaimer

Market data, signals, backtests, simulated fills and model outputs are for research and educational use. They do not constitute financial advice or guarantee future results.
