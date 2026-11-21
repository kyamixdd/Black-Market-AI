# BlackMarket AI - Security Documentation

This document outlines the security measures, constraints, and best practices for BlackMarket AI.

## Security Constraints (Non-Negotiable)

### 1. No Real Trading Capabilities
- ❌ **No Binance Order Endpoints**: Only public market data APIs are used
- ❌ **No API Key Authentication**: All data is from public Binance endpoints
- ❌ **No Real Money Execution**: All trading is simulated paper trading
- ❌ **No Access to Private User Data**: No wallet addresses, private keys, or account info

### 2. Model Safety
- ❌ **No Model Modification of Risk Limits**: Risk parameters (position size, leverage, daily loss) are hardcoded in config
- ❌ **No Promotion of Unvalidated Models**: Models must pass walk-forward validation (F1 ≥ 0.50, Accuracy ≥ 0.52)
- ❌ **No Trading on Stale Data**: All signals have freshness validation (default 30 seconds)
- ❌ **No Deleting Losing Trades**: All trades are preserved for analysis and learning
- ❌ **No Fabricated Fills**: All fills are based on realistic market conditions with spread/slippage

### 3. Data Protection
- ❌ **No Exposure of Telegram Credentials**: Tokens stored in .env file (never committed)
- ✅ **Automatic Database Backups**: Daily backups with 30-day retention
- ✅ **Model Checkpoints**: All model versions saved for rollback
- ⚠️ **SQLite Storage**: SQLite is not encrypted by this application; protect database and backup files with OS-level disk encryption and file permissions

### 4. Network Security
- ✅ **Public APIs Only**: Only Binance public REST and WebSocket endpoints
- ✅ **Exchange Rate Limiting**: Exchange client rate limiter respects Binance request weights
- ✅ **Inbound API Rate Limiting**: Per-client sliding-window limits on API and WebSocket connections; web login and backend proxy have additional process-local limits
- ✅ **No Outbound Connections**: Except Binance API and Telegram Bot API
- ✅ **No Inbound Connections**: Application doesn't listen on any ports

### 5. Paper Trading Isolation
- ✅ **Complete Isolation from Live Execution**: No order signing, no API keys for trading
- ✅ **Separate Virtual Portfolios**: Spot (500 USDT) and Futures (500 USDT)
- ✅ **Realistic Simulation**: Fees, slippage, spread, funding, liquidation
- ✅ **State Persistence**: Automatic save/restore on startup/shutdown

## Architecture Security

### Component Isolation
```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Scanner  │  │Intelligence│ │ Simulator│  │  Telegram  │  │
│  │ (read)   │  │  (read)   │  │ (write)  │  │  (notify)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Binance Public│    │   SQLite DB   │    │  Telegram Bot │
│   REST/WS     │    │  (encrypted)  │    │   API (opt)   │
└───────────────┘    └───────────────┘    └───────────────┘
```

### Data Flow Security

1. **Market Data Ingestion**: Public Binance API → Rate Limiter → Local Cache → Database
2. **Signal Generation**: Indicators → Strategies → Validation → Event Bus → Simulator
3. **Trade Execution**: Simulator ONLY (no external API calls)
4. **Learning**: Predictions → Outcomes → Training → Validation → Promotion (gated)
4. **Notifications**: Orchestrator → Telegram Client → Bot API (optional)

## Configuration Security

### Environment Variables (.env)
```env
# NEVER COMMIT THIS FILE TO VERSION CONTROL
TELEGRAM_BOT_TOKEN=your_bot_token_here  # Keep secret
TELEGRAM_CHAT_ID=your_chat_id_here      # Keep secret
DATABASE_URL=sqlite:///data/blackmarket.db
```

### Hardcoded Safety Limits (config.py)
```python
# These CANNOT be modified by ML models
RISK_PER_TRADE_PCT = 0.5          # Max 0.5% per trade
RISK_MAX_DAILY_LOSS_PCT = 2.0     # Max 2% daily loss
RISK_MAX_LEVERAGE = 3.0           # Max 3x leverage
MAX_SPOT_POSITIONS = 5            # Max 5 spot positions
MAX_FUTURES_POSITIONS = 5         # Max 5 futures positions
MIN_VALIDATION_F1 = 0.50          # Minimum F1 for model promotion
MIN_VALIDATION_ACCURACY = 0.52    # Minimum accuracy for promotion
```

## Threat Model

### Threats Considered

| Threat | Likelihood | Impact | Mitigation |
|--------|------------|--------|------------|
| API Key Leak | N/A | Critical | No API keys used |
| Real Trading | N/A | Critical | No order endpoints |
| Model Manipulation | Low | High | Validation gates |
| Data Corruption | Medium | Medium | Daily backups |
| Telegram Token Leak | Low | Medium | .env file, not committed |
| Memory Exhaustion | Low | Medium | Rate limiting, limits |

### Threats NOT Considered (Out of Scope)

- Physical access to machine
- OS-level compromise
- Supply chain attacks on dependencies
- Side-channel attacks

## Security Checklist

### Pre-Deployment
- [ ] Verify no API keys in codebase
- [ ] Verify no hardcoded secrets
- [ ] Verify .env is in .gitignore
- [ ] Verify Telegram token not in logs
- [ ] Verify OS-level disk encryption and restrictive permissions on database and backup directories
- [ ] Verify API and login rate limits are configured for the deployment
- [ ] Verify rate limiting active

### Runtime
- [ ] Monitor for unusual API requests
- [ ] Check daily backup completion
- [ ] Verify model validation gates
- [ ] Monitor disk space for backups
- [ ] Review system event logs

### Post-Deployment
- [ ] Rotate Telegram token if compromised
- [ ] Update dependencies regularly
- [ ] Review and test recovery procedures
- [ ] Audit model promotion history

## Dependency Security

### Approved Dependencies
All dependencies are pinned in `requirements.txt` and `pyproject.toml`:

```text
aiohttp==3.14.5
websockets==15.0
python-dotenv==1.1.0
pydantic==2.11.0
sqlalchemy==2.0.40
aiosqlite==0.21.0
numpy==2.3.0
pandas==3.1.1
scipy==1.18.1
scikit-learn==1.9.1
xgboost==3.4.1
river==0.27.0
joblib==1.6.0
ta==0.11.0
rich==14.0.0
textual==3.0.0
```

### Dependency Verification
```bash
# Check for vulnerabilities
pip audit

# Verify package integrity
pip install --require-hashes -r requirements.txt
```

## Incident Response

### If Telegram Token Compromised
1. Immediately revoke token via @BotFather
2. Generate new token
3. Update .env file
4. Restart application

### If Database Corrupted
1. Stop application
2. Restore from latest backup
3. Verify data integrity
4. Restart application

### If Model Behaves Unexpectedly
1. Disable ML: `ML_ENABLED=false`
2. Rollback model: `trainer.rollback_model()`
3. Review learning run logs
4. Re-enable after investigation

## Compliance

### Data Handling
- No personal data collected
- No financial advice given
- Paper trading only
- Educational/research purpose

### Regulatory
- Not a financial service
- Not an investment advisor
- No real money handling
- No customer data

## Security Contacts

For security issues:
1. Do NOT create public issues
2. Contact maintainers directly
3. Include reproduction steps
4. Allow time for fix before disclosure

## Application-Level Web Security

- Web login rejects cross-origin requests and applies per-IP password-attempt throttling.
- Web backend proxy requires a valid signed, HttpOnly session and checks the Origin header on state-changing requests.
- Session cookies use Secure in production and SameSite=Strict; signed claims include issued-at, expiry and a random nonce.
- The local API requires a bearer token, applies per-client request limits, and rejects remote clients unless remote API mode is explicitly enabled.
- WebSocket handshakes are authenticated and rate-limited. Browser-facing state changes are additionally constrained by same-origin validation at the web proxy.
- In-memory rate limits are per application process and reset on restart; use an upstream gateway for distributed deployments.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-01-01 | Initial security documentation |

---

**Remember**: This is a paper trading research system. No real money is ever at risk. The security model is designed around this principle.