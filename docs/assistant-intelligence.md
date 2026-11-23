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

## Stage 1 request orchestration

The API route delegates request execution to `assistant_runtime.execute_assistant_query`. The runtime coordinates the existing deterministic tool selector, input validation, evidence tool execution, result summarization, and optional provider interpretation.

Each request receives a unique task ID and an in-request lifecycle trace:

`received → interpreting → executing → validating → completed`

Validation or execution exceptions move the trace to `failed` and are re-raised to the API boundary. The trace is bounded to the current request and is not represented as durable task storage.

The runtime does not calculate market indicators, change paper-trading state, grant permissions, or execute arbitrary code. Existing allowlisted evidence tools remain authoritative. Multi-step planning, persistent memory, feedback learning, event-driven monitoring, and cancellation are not implemented by this stage.

## Optional compatible provider

A provider can add a short interpretation to the deterministic evidence. It is disabled by default. Configure these backend environment variables only if a compatible service is available:

- `BLACKMARKET_ASSISTANT_PROVIDER=openai_compatible`
- `BLACKMARKET_ASSISTANT_API_URL=https://your-compatible-endpoint/v1`
- `BLACKMARKET_ASSISTANT_MODEL=your-model-name`
- `BLACKMARKET_ASSISTANT_API_KEY=...` (optional for local/self-hosted endpoints)

Keep the key in backend environment configuration; never place it in frontend variables or commit it. The compatible endpoint must expose `POST /chat/completions`. Provider timeouts or errors fall back to the deterministic answer. Provider text is labeled as interpretation, not verified fact.

The assistant uses the same authenticated `/api/assistant/query` endpoint as other API routes. Inputs are bounded and symbol, market, and timeframe are validated.
