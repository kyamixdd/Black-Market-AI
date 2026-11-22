# BlackMarket AI

Local-first cryptocurrency market analysis, strategy research and paper-trading application.

BlackMarket AI combines public Binance market data, technical analysis, strategy evaluation, simulated execution, risk controls and local learning tools. The supported desktop product runs a Tauri shell with a supervised Python backend. Trading is simulated; the application does not submit real exchange orders.

## Repository status

- Development branch: `black-market-ai-beta`
- Branch head reviewed: `ee602590442d9d29060d525e1aff5539dc42f01c`
- Latest branch CI: [run #605](https://github.com/kyamixdd/Black-Market-AI/actions/runs/45055409152)
- CI result: success for the reviewed commit
- Product version: `1.0.0`
- Release classification: desktop beta candidate; hosted website private preview

The CI run completed the Python regression suite, dependency audit, desktop TypeScript/lint/market-data tests, shared website build, Rust/Tauri compile checks, responsive browser smoke tests and Windows bundled-backend/NSIS install smoke test.

CI success verifies the jobs listed in the workflow. It does not establish profitability, signed distribution, full manual Windows acceptance or a live hosted backend deployment.

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
- `core/`, `market_data/`, `strategies/`, `paper_trading/`, `risk/`, `learning/` — Python engine components.
- `tests/` — backend, frontend-service and subsystem regression tests.
- `.github/workflows/` — CI, hosted smoke test and desktop release workflows.
- `docs/` — product-specific technical and operating documentation.

## Desktop development

Requirements include Python 3.10+, Node.js/npm, Rust and the Tauri platform prerequisites. Windows installer builds require the Windows SDK, MSVC build tools and WebView2.

Create a Python environment and install the project dependencies:

```bash
python -m venv .venv
# Windows PowerShell
.venv\\Scripts\\Activate.ps1
# macOS/Linux
source .venv/bin/activate
python -m pip install -r requirements.txt
```

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

The browser-only Vite preview serves the frontend and does not supervise the Python backend. Use Tauri to verify desktop-managed startup and shutdown.

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

SQLite databases, model artifacts and backup archives are not application-encrypted. Protect local data using OS-level encryption and access controls. See [Backup and Recovery](BACKUP_GUIDE.md).

## License and distribution

BlackMarket AI is proprietary software. All rights reserved. No permission is granted to copy, modify, redistribute, sublicense, or create derivative or competing products from this source code without prior written permission. See [LICENSE](LICENSE).

The public GitHub repository is source-visible; repository access is not a commercial software license. The commercial product is intended to be distributed as an application, subject to a separate end-user license agreement (EULA). Third-party components remain subject to their own licenses.

Public release also requires the acceptance items in [RELEASE_READINESS.md](RELEASE_READINESS.md), including installer/source identity, Windows upgrade/uninstall checks, signing status disclosure, security review and release artifact verification.

## Documentation

- [Release readiness](RELEASE_READINESS.md)
- [Security policy and threat model](SECURITY.md)
- [Backup and recovery](BACKUP_GUIDE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Release and hosting procedures](docs/RELEASING_AND_HOSTING.md)
- [Project status and audit](docs/PROJECT_STATUS.md)
- [Market-intelligence assistant](docs/assistant-intelligence.md)
- [Community strategy library](docs/COMMUNITY_STRATEGY_LIBRARY.md)

## Disclaimer

Market data, signals, backtests, simulated fills and model outputs are for research and educational use. They do not constitute financial advice or guarantee future results.