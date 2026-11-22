# BlackMarket AI

**Local-first cryptocurrency market intelligence and paper-trading research platform**

> **Paper trading only.** The application is designed for simulated Spot and USDⓈ-M Futures trading. It does not place real exchange orders and does not require Binance trading credentials.

## Project status (22 November 2026)

- **Current development branch:** `black-market-ai-beta`
- **Audited branch head:** `db3fc448af100236efac42ee8ed8e2fbe6a162d7`
- **Latest promotion to `main` observed:** `07817c4` (PR #32)
- **Latest GitHub Actions run observed for the branch head:** CI run #343 — success
- **Current release assessment:** Desktop beta candidate; not yet a broadly supported public release. The hosted website remains a private-preview path.

The score and readiness notes in [RELEASE_READINESS.md](RELEASE_READINESS.md) are an engineering assessment, not a guarantee of trading performance or security certification.

## What it does

BlackMarket AI combines public exchange market data, multi-timeframe analysis, strategy signals, a paper-trading simulator, risk controls, and a local learning pipeline.

### Main capabilities

- Public Binance Spot and USDⓈ-M Futures market data.
- Symbol discovery, market scanning, candle history, and nine configured timeframes (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w).
- Technical analysis including RSI, MACD, ADX, ATR, VWAP, moving averages, Bollinger Bands, and market-regime context.
- Five strategy families: Momentum, Breakout, Trend Following, Mean Reversion, and Reversal.
- Market breadth, relative strength, volatility/ATR, quote-volume comparisons, and freshness indicators where sufficient source data is available.
- Paper Spot and Futures portfolios with simulated fees, spread, slippage, funding, leverage, liquidation, stop-loss/take-profit, limit orders, and partial position management.
- Risk limits for trade sizing, daily loss, total open risk, leverage, and position counts.
- Learning infrastructure using RandomForest, XGBoost, and River, with chronological validation, confidence calibration, economic evidence, and gated model promotion.
- SQLite persistence, integrity checks, backup/recovery, and a Textual terminal dashboard.
- Optional Telegram notifications.

**Important:** An implemented strategy or a passing backtest is not evidence of future profitability. Market metrics can be unavailable when the required history is missing; the UI should show that state rather than invent a value.

## Supported product paths

### Windows desktop — primary product path

The primary user experience is the Tauri desktop application with its supervised local backend. The Windows installer pipeline now builds a bundled backend executable; a clean-installer CI smoke test installs and starts the app with Python removed from `PATH`.

For users, install the published Windows NSIS release artifact when one is available. Do not use an intermediate CI artifact as a stable public release.

For developers, build from a Windows environment with the required Rust/Tauri, Node/npm, MSVC C++ build tools, Windows SDK, and WebView2 prerequisites:

```powershell
./scripts/build_windows_installer.ps1
```

The installer is produced under:

`blackmarket-desktop/src-tauri/target/release/bundle/nsis/`

The installer workflow and clean-machine smoke test are covered by CI. Before a public stable release, verify the exact release artifact, version, signing status, upgrade/uninstall behavior, and supported Windows versions.

### Website — private preview, not production-hosted service

The Next.js website imports the same canonical React dashboard as the desktop app. It uses a server-side login/session layer and a same-origin backend proxy; browser code must never receive the backend bearer token.

The website requires server-side configuration:

- `BLACKMARKET_BACKEND_URL`
- `BLACKMARKET_SESSION_SECRET` (at least 32 random characters)
- `BLACKMARKET_WEB_PASSWORD`
- `BLACKMARKET_API_TOKEN`

The backend host must explicitly enable remote API mode, require the same high-entropy bearer token, use HTTPS, and configure durable storage. Remote API mode is disabled by default.

The website login is a **single-password private-preview gate**, not multi-user identity, role-based authorization, or a managed public SaaS account system. The hosted backend and deployment must pass end-to-end authentication, persistence, data-freshness, event-stream, portfolio, and rejected-order tests before being advertised as production-ready.

See [blackmarket-web/README.md](blackmarket-web/README.md) for deployment configuration.

## Legacy CLI / terminal mode

The Python terminal application remains available for development and local use.

### Requirements

- Python 3.10+
- Internet access for public Binance market data
- Windows, macOS, or Linux for the Python/CLI path

### Setup

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows, the repository also provides installer/run/test scripts. Review scripts before running them and keep personal credentials out of the repository.

### Run

```bash
python main.py
```

For the Tauri desktop development app:

```bash
cd blackmarket-desktop
npm ci
npm run tauri:dev
```

The browser-only Vite preview does not supervise the local Python backend; use Tauri to verify desktop-managed startup.

## Configuration and secrets

Copy `.env.example` to `.env` for the Python/desktop backend. Telegram is optional and disabled by default. Never commit `.env`, Telegram credentials, session secrets, or backend bearer tokens.

The desktop API binds to loopback by default (`127.0.0.1:8765`) and requires bearer authentication. Do not enable remote API mode on an untrusted network. The website's credentials must remain server-side.

See [SECURITY.md](SECURITY.md) for the threat model, security limitations, and release checklist.

## Testing

### Python regression suite

```bash
python -m pytest -q -m "not live"
```

Live exchange smoke tests are marked separately because they depend on external service availability.

### Desktop frontend

```bash
cd blackmarket-desktop
npm ci
npm run build
npm run lint
npm test
```

### Windows installer

```powershell
./scripts/build_windows_installer.ps1
```

The GitHub Actions workflow checks the Python backend, desktop TypeScript/lint/tests, website build, and Windows installer startup/shutdown smoke test. CI success is necessary but does not replace manual release acceptance or a live market-data check.

## Data, backups, and recovery

The application stores local application state in SQLite. Database files and backups are **not encrypted by the application**; use OS-level disk encryption and restrictive account permissions.

The recovery subsystem verifies database integrity and creates compressed backups according to configured backup behavior. Preserve the original database and SQLite sidecar files before attempting manual recovery. Test restoration on a copy, not on the only original.

## Documentation

- [Security policy and threat model](SECURITY.md)
- [Development progress and historical implementation log](DEVELOPMENT_PROGRESS.md)
- [Backup and recovery guide](BACKUP_GUIDE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Release readiness audit and pre-release checklist](RELEASE_READINESS.md)
- [Website deployment guide](blackmarket-web/README.md)

## Disclaimer

BlackMarket AI is a software research and paper-trading project, not financial advice or an investment service. Simulated fills, historical tests, and machine-learning scores do not represent actual execution or guarantee results. Use at your own risk.
