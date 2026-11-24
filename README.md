# BlackMarket AI

Local-first cryptocurrency market analysis, strategy research and paper-trading application.

BlackMarket AI combines public Binance market data, technical analysis, strategy evaluation, simulated execution, risk controls and local learning tools. The supported desktop product runs a Tauri shell with a supervised Python backend. Trading is simulated; the application does not submit real exchange orders.

## Current audit state — 23 November 2026

- Product version: `1.0.0`.
- Product classification: Windows desktop beta candidate; hosted website private preview.
- The current local Git repository has no commits; application files are uncommitted. A branch, commit identity, remote CI result, or release artifact cannot be verified from this workspace.
- The local source test/build checks are recorded in [Project Status](docs/PROJECT_STATUS.md). They do not verify a hosted deployment, production Binance stream, installer acceptance, financial performance, or security certification.
- A non-placeholder Telegram token was present in `.env.example` during this audit and has been removed. Treat it as compromised and rotate/revoke it before release. See [SECURITY.md](SECURITY.md).
- Public release remains blocked by the open items in [Release Readiness](RELEASE_READINESS.md), including accurate risk-assessment metrics, clean source provenance, and release-artifact verification.

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
- Textual terminal interface and Tauri desktop interface.

Feature availability depends on configured runtime mode and the data available for the selected asset/timeframe. The application reports unavailable or insufficient data rather than treating it as a valid measurement.

## Application structure

- `blackmarket-desktop/` — shared React/TypeScript dashboard and Tauri desktop shell.
- `blackmarket-web/` — Next.js private-preview website, login/session handling and same-origin backend proxy.
- `src_tauri/backend/` — FastAPI backend, orchestration bridge, market engine and API routes.
- `core/`, `market/`, `exchange/`, `strategies/`, `paper_trading/`, `risk/`, `learning/` — Python engine components.
- `tests/` — backend, frontend-service and subsystem regression tests.
- `.github/workflows/` — CI, hosted smoke test and desktop release workflows.
- `docs/` — product-specific technical and operating documentation.

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

The browser-only Vite preview serves the frontend and does not supervise the Python backend. `npm run tauri:dev` uses a development-only CSP override for Vite HMR; packaged builds use the restrictive production CSP. Use Tauri to verify desktop-managed startup and shutdown.

Build the Windows installer from the repository root:

```powershell
./scripts/build_windows_installer.ps1
```

The installer output is under `blackmarket-desktop/src-tauri/target/release/bundle/nsis/`.

## Website private preview

The Next.js website imports the shared dashboard. It uses a server-side single-password session and a same-origin proxy to a separately hosted FastAPI backend.

Required server-only configuration:

- `BLACKMARKET_BACKEND_URL`
- `BLACKMARKET_API_TOKEN`
- `BLACKMARKET_SESSION_SECRET`
- `BLACKMARKET_WEB_PASSWORD_HASH`

The website is not a multi-user account system and is not approved as a public hosted service. A live backend, durable storage, authentication, streaming and paper-trading workflow must be verified before enabling public access. See [website setup](blackmarket-web/README.md) and [release readiness](RELEASE_READINESS.md).

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
- [Market-intelligence assistant](docs/assistant-intelligence.md)
- [Community strategy library](docs/COMMUNITY_STRATEGY_LIBRARY.md)
- [Complete product, architecture, feature and operating guide](blackmarketai.md)

## Disclaimer

Market data, signals, backtests, simulated fills and model outputs are for research and educational use. They do not constitute financial advice or guarantee future results.
