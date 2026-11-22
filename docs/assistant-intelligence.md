# Local Market Intelligence Assistant

The assistant's deterministic mode is enabled by default and requires no API key, paid service, or external model. It reads only data available through the authenticated local backend.

## Supported evidence tools

- Market snapshot and data freshness
- Historical completed candles
- Backend indicator report
- Scanner status
- Persisted signals and reasons
- Strategy metrics and weights
- Paper account equity and P&L
- Open paper positions and closed paper trades
- Risk status
- Learning status and recorded prediction outcomes

Unavailable records are reported as unavailable rather than fabricated. The assistant does not place orders, change balances, change risk settings, or access real-money accounts.

## Optional compatible provider

A provider can add a short interpretation to the deterministic evidence. It is disabled by default. Configure these backend environment variables only if a compatible service is available:

- `BLACKMARKET_ASSISTANT_PROVIDER=openai_compatible`
- `BLACKMARKET_ASSISTANT_API_URL=https://your-compatible-endpoint/v1`
- `BLACKMARKET_ASSISTANT_MODEL=your-model-name`
- `BLACKMARKET_ASSISTANT_API_KEY=...` (optional for local/self-hosted endpoints)

Keep the key in backend environment configuration; never place it in frontend variables or commit it. The compatible endpoint must expose `POST /chat/completions`. Provider timeouts or errors fall back to the deterministic answer. Provider text is labeled as interpretation, not verified fact.

The assistant uses the same authenticated `/api/assistant/query` endpoint as other API routes. Inputs are bounded and symbol, market, and timeframe are validated.
