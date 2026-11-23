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


## Stage 3 persistent memory

Persistent assistant memories use the existing SQLAlchemy database and `assistant_memories` table. Database initialization creates the table additively through the existing metadata initialization; existing application tables and records are preserved.

Memory categories are `working`, `episodic`, `semantic`, and `procedural`. Records include a generated ID, owner namespace, content, source, importance, confidence, tags, version, access count, creation/update/access timestamps, and optional expiration.

### Memory operations

- `POST /api/assistant/memories`: explicitly save a memory.
- `GET /api/assistant/memories`: list the owner's bounded memory records.
- `GET /api/assistant/memories?query=...`: retrieve relevant records using keyword overlap, tags, importance, confidence, and recency.
- `GET /api/assistant/memories/{memory_id}`: read a memory owned by the caller.
- `DELETE /api/assistant/memories/{memory_id}`: delete a memory owned by the caller.
- Assistant query supports explicit `remember that ...` and `what do you remember about ...` commands.

Memory content is validated and capped at 1200 characters. Credential-like patterns are rejected. Working memories expire by default after one day; optional TTL is bounded to 365 days. Expired records are removed on access/list cleanup. Retrieval is bounded to 10 records and candidate scans are capped. Matching same-owner, same-category content is deduplicated and versioned.

### Ownership and privacy

The local API bearer credential is hashed to derive the memory owner namespace. Raw credentials are not stored. All read/update/delete operations are scoped to that owner. In the current local-token architecture, credential rotation creates a new memory namespace; user-account identity and hosted multi-user identity integration are not yet implemented.

Retrieved memory content is returned as contextual data, not executable instructions. The assistant query response includes a bounded `memory_context` field. Deterministic market calculations and tool permissions are not influenced by memory contents.

### Current limitations

- Automatic conversation summarization and durable conversation history are not implemented.
- Retrieval currently uses lexical overlap and metadata scoring; vector search is not enabled.
- Memory context is exposed to the assistant API, but deterministic response wording does not yet adapt to stored preferences.
- Cross-device account synchronization is not implemented.
- User correction is supported by updating a memory through its ID; automatic contradiction resolution is not implemented.


## Stage 4 controlled tool registry

Assistant evidence operations are dispatched through `src_tauri/backend/assistant_tool_registry.py`. The registry exposes the existing deterministic backend capabilities through stable identifiers; it does not duplicate market, analytics, strategy, portfolio, or risk calculations.

### Registered capabilities

The registry currently includes read-only tools for market snapshots, historical candles, indicator reports, scanner status, signal reports, strategy reports, paper-account summaries, open paper positions, paper-trade history, risk status, and model learning/evaluation status.

Each tool declares a description, input and output schema, required read permission, timeout, availability, and state-change policy. Input validation rejects missing or unsupported fields, invalid symbols, unsupported markets, and unsupported timeframes. Execution is bounded by a timeout and validates the returned tool identifier and result envelope.

### Security boundary

- Only registered tool IDs are accepted.
- The current registry exposes read-only tools only.
- State-changing tools are rejected by the registry.
- Tool permission scopes are checked before execution.
- The current local assistant API grants a limited set of read scopes after bearer authentication; granular account scopes and hosted account identity are not yet wired into the auth layer.
- Tool errors are returned with safe error codes; internal exceptions are not forwarded.
- Tool execution metadata records an execution ID, tool ID, duration, and read-only/state-change flags.
- `GET /api/assistant/tools` returns authenticated tool metadata for client capability display.

### Verification coverage

The Stage 4 registry tests cover successful dispatch, unknown tool rejection, schema validation, permission denial, state-changing tool rejection, timeout handling, malformed tool results, and explicit read-only metadata. Runtime regression tests verify the assistant continues to use existing evidence services through the registry.

### Limitations

The registry currently covers the existing assistant evidence tool set. Additional existing services such as alert management, workspace notes, model registry administration, monitoring subscriptions, and health endpoints require separate reviewed schemas and permission mapping before registration. No write or exchange execution tools are registered.
