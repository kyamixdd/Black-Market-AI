# BlackMarket AI

**Local autonomous market research and paper trading simulation platform**

⚠️ **PAPER TRADING ONLY** - No real money execution. No API keys required.

## Overview

BlackMarket AI is a comprehensive cryptocurrency market intelligence system that autonomously discovers, analyzes, and simulates trading strategies across Binance Spot and Futures markets. The system uses hybrid machine learning (RandomForest + XGBoost + River online learning) to generate trading signals and execute paper trades with realistic simulation including fees, slippage, funding, and liquidation risks.

### Key Features

- 🚀 **Market Discovery**: Discovers currently eligible Spot and USDⓈ-M Futures symbols dynamically from Binance public APIs
- 📊 **Multi-Timeframe Analysis**: 9 timeframes (1m to 1w) with technical indicators (RSI, MACD, ADX, VWAP, etc.)
- 🧠 **Hybrid ML**: Ensemble models with online learning and walk-forward validation
- 🎯 **Strategy Engine**: 5 strategy families (Momentum, Breakout, Trend Following, Mean Reversion, Reversal)
- 💰 **Paper Trading**: Realistic simulation with spread, slippage, fees, funding, and liquidation
- 📱 **Telegram Integration**: Real-time notifications for signals, positions, and system status
- 📺 **Terminal Dashboard**: Live TUI with 11 views (portfolio, signals, positions, learning, etc.)
- 🔄 **Learning Loop**: Predictions → Outcomes → Training → Model promotion
- 🛡️ **Risk Management**: Position limits, daily loss protection, leverage controls
- 💾 **State Persistence**: Automatic database backups and recovery

## Requirements

- **Python**: 3.10 or higher (Python 3.12 is the CI-tested version; other versions should be validated with the pinned dependencies)
- **Operating System**: Windows 10+, macOS 10.14+, or Linux (Ubuntu 18.04+)
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Disk**: 500MB for application, additional space for historical data
- **Network**: Internet connection for Binance API access

## Installation

### Quick Start (Windows)

```powershell
# Download and extract BlackMarket AI to your desired location
# Open PowerShell in the extracted folder and run:
.\install_windows.ps1
```

### Quick Start (macOS/Linux)

```bash
# Download and extract BlackMarket AI to your desired location
# Open terminal in the extracted folder and run:
chmod +x install_unix.sh
./install_unix.sh
```

### Manual Installation

1. **Clone or extract the project**
   ```bash
   cd /path/to/BlackMarket-AI
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Activate virtual environment
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your preferred text editor
   ```

5. **Create required directories**
   ```bash
   mkdir -p data models logs backups
   ```

## Configuration

Edit the `.env` file to customize your setup:

```env
# System
APP_NAME=BLACKMARKET_AI
APP_ENV=development
LOG_LEVEL=INFO

# Exchange (Public APIs only - no keys needed)
BINANCE_MARKET_DATA_ONLY=true

# Market Scanning
SCAN_ALL_ELIGIBLE_SYMBOLS=true
SPOT_ENABLED=true
USDM_FUTURES_ENABLED=true

# Timeframes
TIMEFRAMES=1m,3m,5m,15m,30m,1h,4h,1d,1w

# Paper Capital (total virtual capital split across Spot and Futures)
VIRTUAL_CAPITAL=500
PAPER_TRADING_ENABLED=true

# Risk Management
RISK_PER_TRADE_PCT=0.5
RISK_MAX_DAILY_LOSS_PCT=2.0
RISK_MAX_LEVERAGE=3
MAX_SPOT_POSITIONS=5
MAX_FUTURES_POSITIONS=5

# Learning
LEARNING_MODE=hybrid
ML_ENABLED=true
AUTO_MODEL_TRAINING=true
MODEL_VALIDATION_REQUIRED=true
MODEL_RETRAIN_MIN_DAYS=7
MODEL_RETRAIN_MIN_NEW_SAMPLES=100

# Telegram (Optional; disabled by default)
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Hosted dashboard authentication (optional for local-only desktop use).
# If using the hosted Render dashboard, set this to the SAME 64-character hex
# token configured as BLACKMARKET_API_TOKEN in Render. Keep it private.
BLACKMARKET_API_TOKEN=

# Database
# Leave DATABASE_URL unset to use the selected local application-data directory.
```

### Telegram Bot Setup

Telegram is optional. Leave `TELEGRAM_ENABLED=false` to run the core application without bot credentials; set it to `true` only after configuring both values below.

1. Create a bot with [@BotFather](https://t.me/BotFather)
2. Get your bot token
3. Get your chat ID by sending a message to your bot and using:
   ```bash
   curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | jq '.result[0].message.chat.id'
   ```

## Running the Application

### Desktop Dashboard (Tauri)

Launch the BlackMarket AI desktop executable or its shortcut as the primary experience. The desktop application starts and supervises the local FastAPI backend. It checks backend, database, and WebSocket readiness before showing market data; a startup failure displays diagnostics and a retry action instead of placeholder dashboard values. Only one desktop instance is allowed, and closing the app stops a backend process that it started.

The Tauri bundle is configured to include the Python source, but it does **not** bundle a Python interpreter or the Python package environment. Install Python 3.10+ and the project dependencies first. Python 3.12 is the CI-tested runtime; Python 3.14 has not yet been verified against the complete dependency set. On Windows, run `.\install_windows.ps1` from the project directory; it installs `src_tauri\backend\requirements.txt` into the project's `venv`, which the desktop supervisor can use. For another interpreter, set `BLACKMARKET_PYTHON` to its executable and install the backend requirements there. A missing interpreter or dependency is reported in the startup screen and backend log.

The desktop backend binds only to `127.0.0.1:8765`. If the hosted dashboard will connect through a private tunnel later, place the same `BLACKMARKET_API_TOKEN` used in Render in the project's private `.env` file; the desktop supervisor reads it without logging the value. Otherwise it creates a private per-install token for desktop-only use. Desktop data, configuration, and logs use the current user's application-data directory; the startup screen shows the backend log location when available. The desktop app does not require Binance credentials and does not provide real-money trading.

For desktop development on Windows, install the Tauri prerequisites (Rust and Visual Studio C++ Build Tools), then run:

```powershell
cd .\blackmarket-desktop
npm ci
npm run tauri:dev
```

The browser preview (`npm run dev`) cannot start the Python backend; use the Tauri desktop app to test managed startup.

To build the Windows NSIS installer from a Windows development environment with Rust 1.90+, the MSVC C++ build tools and Windows SDK, and WebView2 installed:

```powershell
cd .\blackmarket-desktop
npm ci
npm run tauri:build
```

The configured installer output is under `blackmarket-desktop\src-tauri\target\release\bundle\nsis`. The bundle is configured to include the desktop and Python source, but not a Python runtime or its dependencies; it is not a self-contained production installer until those prerequisites are provisioned for target machines.

#### Windows batch fallback and diagnostics

These scripts are fallback/development tools; they do not start or stop Python directly:

```bat
START_BLACKMARKET.bat
STOP_BLACKMARKET.bat
CHECK_BLACKMARKET.bat
```

`START_BLACKMARKET.bat` launches a built desktop executable when found, or runs the Tauri development app with its console visible for diagnostics. Set `BLACKMARKET_DESKTOP_EXE` to an executable's absolute path to use an installed build outside the project folders. `STOP_BLACKMARKET.bat` requests a graceful desktop close and never force-kills a backend process. `CHECK_BLACKMARKET.bat` reports the desktop process and local API readiness without changing application state.

### Windows Terminal Dashboard

```powershell
# Optional legacy terminal interface
.\run_windows.ps1

# Or directly:
python main.py

# Run tests
.\test_windows.ps1
```

### macOS/Linux

```bash
# Run the application
./run_unix.sh

# Or directly:
python main.py

# Run tests
./test_unix.sh
```

### Terminal Dashboard

The application starts with a live terminal dashboard showing:
- Portfolio overview
- Market scanner status
- Trading signals
- Open positions
- Learning progress
- System health

**Keyboard Shortcuts:**
- `1-0`: Switch between tabs
- `l`: Toggle log view
- `r`: Refresh dashboard
- `space`: Pause/resume updates
- `q`: Quit

## Testing

Run the complete test suite:
```bash
python -m pytest tests/ -v
```

Run specific test phases:
```bash
# Phase 1 - Project Foundation
python -m pytest tests/test_core.py -v

# Phase 2 - Exchange
python -m pytest tests/test_exchange.py -v

# Phase 3 - Market Analysis
python -m pytest tests/test_market_analysis.py -v

# Phase 4 - Intelligence
python -m pytest tests/test_intelligence.py -v

# Phase 5 - Paper Trading
python -m pytest tests/test_paper_trading_phase5.py -v

# Phase 6 - Learning
python -m pytest tests/test_learning_phase6.py -v

# Phase 7 - Dashboard & Telegram
python -m pytest tests/test_phase7_dashboard_telegram.py -v

# Phase 8 - Integration
python -m pytest tests/test_integration_phase8.py -v
```

## Backup and Recovery

### Automatic Backups

The recovery subsystem creates a verified, compressed SQLite backup every six hours and during graceful shutdown, retaining up to 30 backups. The default CLI location is `data/backups/`. In the installed Tauri app, the database and backups use the per-user application data directory (normally `%APPDATA%\\com.blackmarket.ai\\backups`), not the installation directory.

### Manual Backup

Use the application’s verified SQLite backup mechanism rather than copying a database file while the engine is running. Stop the app before performing a manual restore, and preserve the current database before replacing it.

### Recovery

On startup, the application checks database integrity and recovers persisted paper-trading state. If integrity validation fails, it reports the error and preserves the database for recovery rather than silently recreating it.

## Security

### Important Security Constraints

- ❌ **No Binance Order Endpoints**: Only public market data APIs are used
- ❌ **No API Keys Required**: All data is from public Binance endpoints
- ❌ **No Real Money Execution**: All trading is simulated paper trading
- ❌ **No Model Modification of Risk Limits**: Risk parameters cannot be changed by ML models
- ❌ **No Trading on Stale Data**: All signals have freshness validation
- ❌ **No Promotion of Unvalidated Models**: Models must pass walk-forward validation
- ❌ **No Deleting Losing Trades**: All trades are preserved for analysis
- ❌ **No Fabricated Fills**: All fills are based on realistic market conditions
- ❌ **No Exposure of Telegram Credentials**: Tokens are stored in .env file

### Data Protection

- SQLite databases are **not encrypted at rest by default**; protect the Windows/macOS user account and use full-disk encryption where available
- Configuration files (.env) contain secrets and must never be committed to version control
- Backup files are stored locally with timestamps; protect the backup directory as well
- The shared API token is required only when the hosted dashboard must authenticate to the local backend

## Troubleshooting

### Common Issues

1. **Module Import Errors**
   ```bash
   # Ensure virtual environment is activated
   # Check Python version (>=3.10)
   python --version
   ```

2. **Database Issues**
   ```bash
   # Delete corrupted database and reinitialize
   del data/blackmarket.db
   python -c "from database.connection import Database; Database('sqlite:///data/blackmarket.db').init_db()"
   ```

3. **WebSocket Connection Issues**
   - The system automatically retries with exponential backoff
   - Check internet connection
   - Firewalls may block WebSocket connections

4. **Memory Issues**
   - Reduce `MAX_CONCURRENT_SCANS` in config.py
   - Close other applications using memory

5. **Telegram Not Working**
   - Verify bot token and chat ID
   - Check bot permissions
   - Test with `python -c "from notifications.telegram_client import TelegramClient; TelegramClient('token', '123').test_connection()"`

### Debug Mode

Enable debug logging:
```env
LOG_LEVEL=DEBUG
```

### Performance Tuning

- Adjust `TIMEFRAMES` to reduce data processing
- Set `SCAN_ALL_ELIGIBLE_SYMBOLS=false` for faster startup
- Reduce `PREDICTION_HORIZON_MINUTES` for more frequent updates

## Architecture

### Core Components

1. **Orchestrator**: Central coordinator managing all services
2. **Event Bus**: Async message passing between components
3. **Market Scanner**: Discovers and monitors symbols
4. **Intelligence Core**: Generates trading signals
5. **Paper Trading Simulator**: Executes simulated trades
6. **Learning Engine**: Trains ML models from outcomes
7. **Telegram Client**: Sends notifications
8. **Terminal Dashboard**: Real-time monitoring interface

### Data Flow

```
Market Data → Candles → Indicators → Strategies → Signals → Paper Trading → Outcomes → Learning → New Models
```

## Support

- **Documentation**: See DEVELOPMENT_PROGRESS.md for detailed phase-by-phase progress
- **Issues**: Report bugs in your issue tracking system
- **Contributions**: Fork and submit pull requests

## License

This project is for educational and research purposes only. Use at your own risk.

---

**Remember**: This is a paper trading system. No real money is ever at risk.#   B l a c k - M a r k e t - A I  
 