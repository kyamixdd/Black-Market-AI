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

The API route delegates request execution to `assistant_runtime.execute_assistant_query`. The runtime coordinates validated input, evidence tool execution, result summarization, and optional provider interpretation.

Each request receives a unique task ID and an in-request lifecycle trace. The trace is scoped to the current request and is not durable task storage. Errors return a sanitized message and bounded task metadata.

The runtime does not calculate market indicators, change paper-trading state, grant permissions, or execute arbitrary code.

## Stage 2 natural-language understanding

`assistant_nlu.parse_assistant_request` converts a supported request into a structured representation containing:

- Request ID and original/normalized text
- One or more deterministic intent categories and associated registered evidence tools
- Asset symbols, market and timeframe
- Duration expressions and numeric values
- Recognized constraints
- Conversational reference markers
- Confidence level with explanatory signals
- Clarification requirement and question
- Unsupported-request status

The parser uses a bounded deterministic vocabulary and regular-expression extraction. Confidence is categorical and reflects detectable signals; it is not a calibrated probability.

The runtime executes up to three distinct evidence categories sequentially. Multi-asset comparisons are not yet implemented because the current evidence tools accept one asset per call; these requests return a clarification instead of implying a comparison occurred. Requests with missing references or unsupported intent also ask for clarification. The API exposes parsed understanding as additive response metadata.

Context is supplied only when the request explicitly includes symbol or timeframe fields. The API does not yet maintain conversational history across requests; persistent context resolution is deferred to a later stage.

## Optional compatible provider

A provider can add a short interpretation to deterministic evidence. It is disabled by default. Configure these backend environment variables only if a compatible service is available:

- `BLACKMARKET_ASSISTANT_PROVIDER=openai_compatible`
- `BLACKMARKET_ASSISTANT_API_URL=https://your-compatible-endpoint/v1`
- `BLACKMARKET_ASSISTANT_MODEL=your-model-name`
- `BLACKMARKET_ASSISTANT_API_KEY=...` (optional for local/self-hosted endpoints)

Keep the key in backend environment configuration; never place it in frontend variables or commit it. The compatible endpoint must expose `POST /chat/completions`. Provider timeouts or errors fall back to the deterministic answer. Provider text is labeled as interpretation, not verified fact.

The assistant uses the same authenticated `/api/assistant/query` endpoint as other API routes. Inputs are bounded and symbol, market, and timeframe are validated.
