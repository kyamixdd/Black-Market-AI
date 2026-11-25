# BlackMarket AI — Product, Architecture, Features and Operating Guide

## 1. Project identity

BlackMarket AI is a local-first cryptocurrency market research, strategy-development and paper-trading application. It combines public exchange data, market analysis, signal generation, strategy testing, simulated execution, risk controls and a controlled learning pipeline in one workspace.

The production product is the Tauri desktop application with a supervised Python backend. The legacy Next.js source is not a supported production interface; the React/TypeScript dashboard is packaged through the desktop Vite/Tauri build.

**Trading boundary:** BlackMarket AI is paper-trading and simulation software. It does not place real-money exchange orders and does not require private Binance trading credentials for public market-data access.

## 2. Repository baseline and audit method

- Review date: 25 November 2026
- Product version declared by project: `1.0.0`
- Local Git state: branch `Black-Market-AI-Beta-1.0.1` at baseline commit `466dbc7`; the working tree contains uncommitted changes.
- Audit type: source inventory, subsystem tracing, security/persistence/risk/market/ML/API/frontend review, documentation reconciliation, and local test/build checks.
- Runtime limitations: this audit did not verify live production Binance streams, a fresh backtest/model run, installer acceptance, or visual interaction across supported devices.

The inventory contains 226 authored application and test files outside generated build output. Findings below distinguish source implementation, local automated verification, and live deployment/runtime behavior that still requires acceptance testing. Presence of a module or screen is not proof of profitability, prediction quality, or public-hosting readiness.

## 3. Product purpose and user benefits

BlackMarket AI is designed to reduce the fragmentation between market observation and strategy evaluation. Its workflow is:

1. **Discover** market conditions and eligible assets.
2. **Analyze** price, volume, candles, indicators and derivatives context.
3. **Generate and inspect** strategy signals with their evidence.
4. **Research** strategy behavior using historical candles and defined assumptions.
5. **Simulate** order and position management with risk controls.
6. **Review** trade outcomes and strategy adherence.
7. **Evaluate** prediction outcomes and candidate models using chronological validation.
8. **Improve** configuration and research workflows using measured results.

The practical benefit is a connected research process: market data, analysis, backtesting, paper execution and learning use shared application services and persisted records rather than unrelated dashboard widgets.

The application is not an exchange, broker, investment adviser or guaranteed-profit system. Signals and model outputs are research information, not instructions to invest.

## 4. Application architecture

### 4.1 Desktop application

The desktop target consists of:

- **Tauri 2 / Rust shell** — native application lifecycle, desktop window and supervised backend process.
- **React 19 + TypeScript + Vite** — shared dashboard UI.
- **Python FastAPI backend** — authenticated API, orchestration bridge and access to engine services.
- **Bundled Python backend** — packaged with the Windows installer workflow so the desktop application does not depend on a separately installed Python runtime at normal use.
- **SQLite / SQLAlchemy** — local persistent application records.
- **WebSocket and HTTP clients** — market data and frontend/backend communication.

The desktop API defaults to loopback, normally `127.0.0.1:8765`, and requires bearer authentication. Remote API mode is disabled by default.

### 4.2 Browser-only Vite development

The Vite browser preview is a local development aid only. It does not start or supervise the Python engine; start Tauri first and keep the Vite server bound to loopback. The server-side proxy reads the local API token from desktop app data and injects it only for allowed local origins. Packaged production builds are the Tauri desktop application, not a browser-hosted site.

### 4.3 Python engine

The backend coordinates these main service areas:

- `core/` — orchestrator, event bus/models, scheduler, runtime settings, health, observability, disaster recovery and controlled evolution.
- `exchange/` — Binance Spot/Futures clients, symbol discovery/registry, rate limiter and WebSocket manager.
- `market/` — candle management, market cache, scanner, analytics, trend/momentum/volume/order-book/volatility analysis, regime detection, data integrity and reliability.
- `intelligence/` — feature engine, signal/decision validation, confidence handling and strategy selection.
- `strategies/` — strategy interface and strategy families.
- `paper_trading/` — simulator, fees, funding, liquidation, PnL and risk management.
- `learning/` — dataset construction, training, prediction, backtesting, Strategy Lab, walk-forward validation, model lifecycle, comparison, trade review and strategy evolution.
- `monitoring/` — drift monitoring.
- `database/` — SQLite connection, models and repositories.
- `src_tauri/backend/api/` — FastAPI routes, schemas and WebSocket manager.
- `src_tauri/backend/assistant_*.py` — assistant runtime, NLU, memory, planning, intelligence and tool registry.
- `terminal/` — Textual terminal dashboard.
- `notifications/` — optional Telegram integration.

### 4.4 Data flow

1. Public Binance endpoints provide exchange market data.
2. Exchange clients normalize and rate-limit requests.
3. WebSocket updates and REST snapshots feed the market cache and candle services.
4. The scanner selects configured Spot/Futures markets and analysis batches.
5. Market and intelligence services calculate indicators, market conditions and strategy signals.
6. The orchestrator coordinates events, persistence, paper execution and learning records.
7. FastAPI exposes authenticated, validated application data to the dashboard and assistant.
8. SQLite stores market history/records, configuration and paper-trading state; model artifacts are stored separately.
9. The dashboard renders data and displays unavailable/stale states when valid evidence is absent.

## 5. Market data and analysis

### 5.1 Data sources and markets

The application integrates public Binance Spot and USDⓈ-M Futures market data. The repository includes market discovery and symbol registry logic, REST clients, WebSocket multiplexing, rate limiting and connection recovery.

Market data availability depends on exchange access, network conditions, rate limits, symbol eligibility and selected timeframe. A disconnected or stale feed must not be treated as a fresh market observation.

### 5.2 Timeframes

The default configured timeframe set is:

`1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w`

Configuration can be adjusted through the runtime configuration. Analysis is constrained by the historical candle data available for each symbol/timeframe.

### 5.3 Market features

The source tree and project documentation identify the following capability areas:

- Ticker snapshots and 24-hour market summaries.
- Historical OHLCV candles.
- Candle integrity and freshness checks.
- Market breadth and relative strength.
- Volume and momentum analysis.
- Trend and volatility analysis.
- Order-book analysis where the relevant data is available.
- Futures mark price, funding rate and open interest context.
- Long/short ratio and derivatives information where supported by the data service.
- Market regime detection and regime radar.
- Scanner status, signal records and signal explanations.

Exact metric availability varies by route, symbol and stored data. UI panels should display unavailable values as unavailable; they must not manufacture a numerical value to fill a card.

## 6. Strategies, signals and research

### 6.1 Strategy families

The current Strategy Lab registers these strategy families:

- Momentum
- Breakout
- Trend following
- Mean reversion
- Reversal

The strategy interface provides a common way to evaluate a strategy against market features and completed candles. Strategy configuration, weights and signal reasons are exposed through the application’s analysis services.

### 6.2 Signal pipeline

The market and intelligence pipeline evaluates normalized market data, features, strategy output and validation/risk conditions. Signal records include reasons and are persisted for review. The intelligence layer is separate from the paper-trading execution layer; a signal does not itself place an exchange order.

### 6.3 Strategy Lab and backtesting

Strategy Lab runs deterministic backtests over completed historical candles. The documented execution convention is:

- Evaluate the signal at a completed bar close.
- Fill at the next bar open.
- If both stop-loss and take-profit are touched within the same candle, assume stop-loss occurs first.

This conservative intrabar rule avoids optimistic selection when candle data cannot establish the actual path of price inside the bar.

Backtest assumptions include initial capital, sizing mode, risk percentage, fixed notional, maximum position percentage, fee rate, slippage, spread and strategy parameters. Results can be saved and compared through the research services.

Backtest results remain dependent on data coverage and assumptions. They are not equivalent to live execution and do not guarantee future performance.

## 7. Paper trading and risk controls

### 7.1 Simulator

The paper-trading simulator maintains virtual Spot and Futures accounts. It supports simulated order and position lifecycle management and uses dedicated components for:

- Fees.
- Funding.
- Liquidation calculations.
- PnL.
- Risk validation.
- Order/position persistence callbacks.
- Account-state locking for serialized mutations.

The simulator supports manual paper-order workflows through authenticated API routes. The route validates symbol/market/order parameters, requires a sufficiently fresh positive market snapshot, validates stop-loss direction and applies the simulator/risk controls.

Spot is long-only. Futures support long and short simulation. No live exchange execution is registered or intended.

### 7.2 Risk configuration

The runtime configuration includes limits such as:

- Risk per trade.
- Maximum daily loss.
- Maximum aggregate open risk.
- Maximum leverage.
- Maximum Spot and Futures position counts.
- Position-size and per-asset exposure limits.

Risk settings are validated and applied to the simulator. Risk limits are intended to reject an order when account or exposure constraints are exceeded; the ML system does not directly modify risk limits.

### 7.3 Trade/account records

The application stores paper account equity/PnL, open positions, order/trade history and risk status. These records support portfolio, positions, trade history and trade-review panels.

Account consistency and behavior under restart, concurrent requests, unusual price movement and partial order transitions must be covered by regression and acceptance testing. Paper results should be evaluated after fees, slippage, spread and funding assumptions.

## 8. AI assistant: what it is and how it works

### 8.1 Default deterministic assistant

The default assistant is a local, deterministic market-intelligence assistant. It does not require a paid API or an external generative model. It retrieves evidence through the authenticated backend and summarizes existing application records.

Supported evidence tools include:

- Market snapshot and freshness.
- Historical candles.
- Indicator report.
- Scanner status.
- Signals and signal reasons.
- Strategy metrics/weights.
- Paper account summary.
- Open paper positions.
- Closed paper-trade history.
- Risk status.
- Learning/model evaluation status.

It is read-only: it does not place orders, alter balances, modify risk limits, or execute arbitrary Python/shell code.

### 8.2 Natural-language understanding

`assistant_nlu.py` parses a supported request into structured intent, entities, market/symbol/timeframe, numeric/duration parameters, constraints, context markers, confidence category and clarification requirements.

The parser uses a bounded deterministic vocabulary and regular-expression extraction. It is not a general-purpose language model. Confidence levels are categorical and based on observable parser signals; they are not calibrated probabilities.

The runtime can execute up to three distinct evidence categories in one request. Multi-asset comparisons and conversational history resolution across independent requests remain limited. Requests that cannot be resolved safely should ask for clarification rather than silently selecting an interpretation.

### 8.3 Tool registry and planning

`assistant_tool_registry.py` is the allowlisted dispatch boundary. Each registered tool defines its input/output schema, permission, timeout, availability and state-change policy. Current assistant tools are read-only.

`assistant_planning.py` creates bounded task plans with task/step IDs, dependencies, step states, retries and cancellation. Plans are limited to eight steps/tool calls. Failed dependencies block dependent steps; transient failures receive a bounded retry. The task lifecycle is in-process and is not durable across backend restart.

### 8.4 Persistent assistant memory

Assistant memory uses the existing SQLAlchemy database rather than a separate required database. Categories are:

- `working` — short-lived task context.
- `episodic` — relevant interaction/outcome records.
- `semantic` — stable useful facts.
- `procedural` — validated workflow knowledge.

Memory records are owner-scoped and include metadata such as source, importance, confidence, tags, timestamps and optional expiration. Content is bounded to 1,200 characters; credential-like patterns are rejected. Working memory expires by default after one day, and configured TTL is bounded.

Retrieval uses lexical overlap and metadata scoring, with bounded candidate/result counts. Vector search is not enabled. Automatic conversation summarization, contradiction resolution, cross-device synchronization and full durable conversation history are not implemented. Stored memory does not grant permissions or change deterministic calculations.

### 8.5 Optional external provider

An optional OpenAI-compatible endpoint can add a short interpretation to deterministic evidence. It is disabled by default and requires backend-only configuration:

- `BLACKMARKET_ASSISTANT_PROVIDER=openai_compatible`
- `BLACKMARKET_ASSISTANT_API_URL`
- `BLACKMARKET_ASSISTANT_MODEL`
- `BLACKMARKET_ASSISTANT_API_KEY` (optional for a local/self-hosted endpoint)

The endpoint must support `POST /chat/completions`. Provider failures/timeouts fall back to deterministic output. Provider text is labeled as interpretation and is not treated as verified market fact.

The optional compatible provider is not proof of a built-in local LLM. The deterministic assistant and ML prediction models are separate subsystems.

## 9. Machine learning and training

### 9.1 Models

The trainer integrates:

- Scikit-learn RandomForest classifier.
- XGBoost classifier.
- River online-learning model pipeline.

The application also includes prediction, outcome labeling, feature/dataset construction, model management, model registry/lifecycle, performance analysis, strategy comparison and regime-aware performance modules.

### 9.2 Training workflow

The documented trainer workflow is:

1. Build a dataset from stored market and prediction/outcome records.
2. Validate feature and target dimensions.
3. Require aligned timestamps.
4. Require economic metadata for promotion evaluation.
5. Run chronological walk-forward validation with a purge gap.
6. Validate candidate performance against active/champion model evidence.
7. Evaluate promotion criteria.
8. Train/register eligible model artifacts.
9. Record metrics and artifact integrity information.
10. Keep candidate, active and rollback states separate.

Required promotion metadata includes timestamps, actual return, transaction costs, market regime, market type and forecast horizon. Training returns an insufficient-data or validation-failed status when required data is absent or misaligned.

### 9.3 Validation and promotion

The walk-forward validator uses time-ordered splits rather than random shuffling. Model lifecycle utilities support seeded training, SHA-256 artifact verification and held-out classification/calibration metrics.

A candidate is not automatically production-ready because it trained successfully. Promotion depends on the configured validation/promotion gate and evidence. Model performance should be reported separately by strategy, market regime, timeframe and forecast horizon where the available dataset supports it.

The system does not establish that a model is profitable. Classification accuracy alone is insufficient: results must be assessed after fees, slippage and realistic execution assumptions, with out-of-sample data and adequate sample sizes.

### 9.4 Online/adaptive learning

River provides an online-learning component, while outcome records and live-learning services supply feedback from observed outcomes. Adaptive behavior is controlled by the application’s configuration and validation lifecycle. Model updates must not bypass validation, risk controls or promotion requirements.

### 9.5 Model limitations

- Historical labels and data quality constrain model quality.
- A model can overfit or drift when market conditions change.
- Validation is evidence about the tested sample, not a future guarantee.
- A registered model is not necessarily an active/promoted model.
- A training job does not equal successful deployment.
- Results require reproducible dataset, feature, timestamp, cost and artifact metadata.

## 10. Intelligence, strategy evolution and monitoring

The repository includes market-regime detection/radar, strategy evolution/DNA, controlled evolution, drift monitoring, trade review, research persistence and model performance comparison.

Controlled evolution is intended to propose bounded changes based on measured weakness and candidate/baseline reports. It is not unrestricted self-modifying code. Changes require explicit approval and version/rollback handling. The Stage 12 audit document notes that controlled-evolution proposal provenance and stale-proposal checks require hardening before they can be treated as a reliable promotion gate.

Monitoring and drift components can identify changes in model/strategy behavior from recorded metrics. Alerts and conclusions depend on the underlying sample size and data quality.

## 11. Other application features

### Portfolio, positions and trade history
Read paper account balances/equity, open positions, closed trades and PnL. These are simulated account records, not exchange account balances.

### Risk panel
Displays configured limits and current risk/exposure state. A UI value is only authoritative when returned by the backend.

### Activity and system diagnostics
Activity displays persisted application events. Diagnostics is a separate live desktop view that reports supervisor/API/database/WebSocket/scanner/learning/paper-trading status, recent persisted events, a bounded backend process-log tail, and rolling frontend HTTP request/failure/latency metrics. Process logs are redacted and bounded; unknown component state remains unknown. Diagnostics reports observed state, not a guarantee that every function or live exchange feed is correct.

### Learning panel
Displays recorded predictions, outcomes, model status and evaluation results. It should not imply a model has been trained or promoted unless the registry/status confirms it.

### Research and saved workspaces
Research snapshots and workspaces allow analysis/configuration to be retained for later review. Saved data is local to the configured database.

### Community strategy library
The community module supports strategy listing/search/filtering, publishing/updating strategy metadata and rules, immutable version snapshots, favorites, reports and unpublishing. Published report metrics are labeled by provenance such as user-submitted or local-backtest. A digest detects summary changes; it does not independently prove a result.

Community ownership uses a local pseudonymous identifier. Records are not synchronized to a hosted service. No profitability ranking or independent backtest verification is currently awarded.

### Share challenges
The repository contains a share-challenge API and frontend feature area. Shared challenge data must remain limited to the intended public challenge payload; private account/trade records are not automatically included.

### Telegram notifications
Telegram integration is optional and disabled by default. The bot token and chat configuration must remain backend-side. Telegram delivery depends on external service availability.

### Terminal interface
The Textual terminal dashboard provides an additional local interface to the Python application. It shares engine services rather than being a separate exchange execution system.

### Backup and recovery
The recovery subsystem creates SQLite backups using the online backup API, validates backup integrity, and supports listing/creating managed backups. Backup/restore must include the required database, sidecar, model and configuration data. Database files and backup archives are not application-encrypted.

## 12. How to install and run

### Desktop development requirements
- Python 3.12 or newer.
- Node.js/npm.
- Rust/Cargo with an MSVC host.
- Microsoft C++ Build Tools with MSVC, a Windows SDK, and WebView2 for Windows installer builds.

Check existing installations before adding prerequisites. Do not replace a working system Python. Use the project virtual environment for backend dependencies.

### Backend environment
Copy `.env.example` to `.env` and configure the runtime. Important defaults include:

- Spot and USDⓈ-M Futures enabled.
- Configured multi-timeframe analysis.
- Paper trading enabled.
- Real trading disabled.
- Risk limits and virtual starting balances.
- Hybrid learning configuration.
- Telegram disabled.
- SQLite database at `data/blackmarket.db`.
- Local API host set to loopback.

Do not commit `.env` or place credentials in frontend variables.

### Backend tests
```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q -m "not live"
```

### Desktop frontend
```bash
cd blackmarket-desktop
npm ci
npm run build
npm run lint
npm test
npm run tauri:dev
```

The Vite browser preview serves the UI only; it does not supervise the Python backend. Use Tauri to verify desktop-managed backend startup/shutdown.

### Windows installer
```powershell
./scripts/build_windows_installer.ps1
```

The release workflow packages a backend executable and NSIS installer. Release artifact verification must use the exact source commit, manifest and checksum for the published binary.

## 13. Customization

### Runtime configuration
Adjust environment variables in the private runtime configuration. Main categories include markets, scanning, timeframes, paper capital, risk, learning, database path, notifications and API host/security settings. Validate configuration before deployment.

### Intelligence mode
The assistant supports validated modes documented in `docs/STAGE9_INTELLIGENCE_CONFIGURATION.md`:

- `balanced` — default balanced behavior.
- `fast` — smaller tool budget, brief output, provider/memory disabled.
- `research` — up to three evidence tools, memory and provider interpretation enabled.
- `conservative` — limited tool budget, memory enabled, provider and feedback adaptation disabled.

Mode selection changes assistant behavior only. It does not add tools or enable real trading.

### Strategy customization
Extend the strategy interface and register a strategy in the Strategy Lab’s strategy map. Add tests for signal behavior, invalid/missing data, sizing assumptions, and backtest execution. Preserve the completed-bar/next-open fill convention unless a documented, tested execution model replaces it.

### Frontend customization
The canonical desktop dashboard is in `blackmarket-desktop/src`. Update its components/screens and design tokens there; do not add a hosted web target.

### Assistant customization
Add a new assistant capability by:
1. Implementing/reusing an existing deterministic backend service.
2. Defining a bounded tool schema and permission in the registry.
3. Validating arguments and outputs.
4. Keeping the tool read-only unless a reviewed state-changing workflow is explicitly required.
5. Adding parser/planning/runtime tests.
6. Updating the assistant documentation and UI capability display.

Do not expose arbitrary Python, shell, database or exchange actions through assistant tools.

### Provider customization
Use a compatible endpoint only through backend environment configuration. Provider secrets must never be exposed to the browser. Keep deterministic evidence as the source of factual market values.

## 14. Commercialization and revenue options

BlackMarket AI can be monetized as software or a research product, but the current repository does not itself provide a revenue guarantee or completed billing infrastructure. Possible business models include:

- **Desktop license:** one-time purchase or paid major-version upgrade for the packaged application.
- **Pro features:** advanced backtesting, model diagnostics, strategy comparison and enhanced local workflows, with clear feature boundaries.
- **Educational products:** strategy-development tutorials, research templates and training material built around the simulator.
- **Private deployment/licensing:** licensed deployment for research teams, subject to support and data-handling requirements.
- **Community marketplace:** future paid strategy distribution only after authorship, provenance, moderation, licensing and consumer-protection rules are defined.

Do not market the product as a money-making trading bot or promise returns. The defensible commercial value is research workflow, simulation, transparency and strategy evaluation.

## 15. Security, privacy and operational limitations

- Desktop API is loopback-bound by default and bearer-authenticated.
- Remote API mode requires explicit enablement and a high-entropy token.
- SQLite, model artifacts and backup archives are not application-encrypted.
- Market data is public but may be delayed, incomplete or unavailable.
- Telegram/provider credentials must be protected.
- Community records use a local pseudonymous identifier.
- No live trading or exchange private-order execution is supported.
- Backtests and ML outputs are not guarantees of future performance.

## 16. Audit findings and current release state

- `.env.example` contained a non-placeholder Telegram token. It was removed from the template and Telegram is disabled there. Revoke it and review any published Git history or artifacts; a targeted local history scan found a token-shaped value at commit `0415b531e14efa7e03c932a6c1e7ee8492105179`, but external publication history is unknown.
- `risk/adaptive_risk.py` calculates drawdown from persisted high-water-mark evidence and correlation from aligned, validated return observations. Missing or insufficient evidence is reported as unavailable. The main simulator does not currently supply all evidence to the adaptive assessment, so these factors may remain unavailable.
- `REAL_TRADING_ENABLED=true` is rejected at startup. Unused Binance API key/secret configuration was removed; exchange access uses public market-data endpoints and paper execution only.
- Eighty-six backup files and three database-related files are tracked in Git, as are 124 generated Next build files. Ignore rules now prevent newly generated local data from being added, but existing tracked files were left untouched.
- SQLite databases, model files and backup archives are not application-encrypted.
- The legacy Next.js source is not supported for production; its shared backend had no account-level authorization or tenant isolation.
- The scanner configures bounded Binance ticker-stream subscriptions after REST ticker discovery; live production stream availability and recovery have not been verified. The watchdog stall handler logs a stall but does not restart components.
- The project is a desktop beta candidate; public release remains blocked by the open items in `RELEASE_READINESS.md`.

## 17. Local verification evidence

- Python regression tests: 670 passed and 3 live exchange tests deselected on Python 3.13; Python 3.12 was not run locally.
- Python dependency audit reported no known vulnerabilities; `pip check` found no broken requirements. The Python wheel built successfully and included its required backend packages.
- Desktop frontend: 16 service tests and production build passed; lint completed with warnings and the build reported a large main chunk.
- Responsive browser smoke passed at eight viewport widths, checking overflow, primary navigation, chart-settings interaction, and page errors. Full Tauri interaction and keyboard acceptance remain unverified.
- The legacy Next.js source is retained but excluded from CI and desktop packaging; it has no supported production build, start command, or deployment workflow.
- No current-head CI, Tauri installer, production exchange stream, backup restore, or financial-performance test was verified in this workspace. The current Starlette TestClient integration emits an httpx deprecation warning.

The detailed findings, severity, evidence, and recommendations are in `LOCAL_AUDIT_REPORT.md`.

## 18. Primary documentation

- `README.md` — project overview and development setup.
- `RELEASE_READINESS.md` — desktop release gates and current classification.
- `SECURITY.md` — threat model and security controls.
- `BACKUP_GUIDE.md` — backup/restore operations.
- `TROUBLESHOOTING.md` — operational diagnostics.
- `docs/PROJECT_STATUS.md` — implementation baseline and release status.
- `docs/assistant-intelligence.md` — assistant implementation and limitations.
- `docs/COMMUNITY_STRATEGY_LIBRARY.md` — community publication and provenance.
- `docs/STAGE9_INTELLIGENCE_CONFIGURATION.md` — intelligence modes.
- `docs/STAGE12_INTELLIGENCE_AUDIT.md` — intelligence audit findings.
- `docs/RELEASING_AND_HOSTING.md` — desktop release procedures.

## 19. Maintainer summary
For the current screen-to-service map and explicit implemented/partial/unverified boundaries, see `docs/FEATURE_AUDIT.md`. For the generated first-party function-candidate index, see `docs/SYMBOL_CATALOG.md`; symbol presence is not runtime verification.

BlackMarket AI is a substantial local-first market research and paper-trading application with a Tauri desktop UI, Python market engine, Binance public-data integration, strategy research, simulated execution, risk controls, persistence, model lifecycle and a bounded evidence-based assistant.

The desktop application is the only supported production target. The assistant is deterministic by default with an optional compatible provider; the ML pipeline is a separate training and evaluation system. Paper trading is the only execution mode.

The main current repository concerns are release acceptance, risk metric evidence, locally tracked runtime data/build output, and source provenance. Existing tracked data was not removed because the working tree already contains user changes. No profitability, live stream operation, or current-head CI result is claimed by this document.
