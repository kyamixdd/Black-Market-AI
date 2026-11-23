# Stage 9 — Intelligence configuration

Supported modes:
- `balanced`: default balanced behavior, memory and provider interpretation enabled.
- `fast`: one evidence tool, brief response, provider interpretation off, memory off.
- `research`: up to three evidence tools, memory and provider interpretation enabled, detailed response.
- `conservative`: one evidence tool, memory enabled, provider interpretation and feedback adaptation off.

Configuration is validated by `core.intelligence_config.IntelligenceConfig`; unknown fields,
unsupported modes, and out-of-range tool limits are rejected. Runtime loading reads
`intelligence_mode` and `intelligence_config` from the private runtime settings store.
`BLACKMARKET_INTELLIGENCE_MODE` can override the persisted mode for deployment-level
configuration. Explicit loader overrides take precedence over persisted values.

The runtime configuration is cached for the process. Call
`reload_runtime_intelligence_config()` after applying a settings change to refresh it.
These settings govern assistant behavior only; they do not enable live trading,
bypass tool allow-lists, or change exchange permissions.


## Settings UI and API

The desktop Settings screen exposes the mode selector and saves it through the authenticated
local API. The API uses \`GET /api/settings/intelligence\` and
\`PUT /api/settings/intelligence\`. The typed frontend client exposes
\`getIntelligenceConfig()\` and \`updateIntelligenceConfig()\`.

Mode tool budgets and provider interpretation are applied to subsequent assistant requests.
All tools still pass through the existing allow-listed registry; no mode grants new tools
or changes paper/live trading permissions. Persisted settings remain in the existing
private runtime settings file, written atomically.


## Current repository status — 23 November 2026

Maintained against `black-market-ai-beta`; application-source baseline reviewed: `49e6841215303ed296ced4fc1ef3039b9959426d`. Later commits in this branch are documentation-only at the time of this update. Verify the branch head before relying on this snapshot as current runtime or CI evidence.

**Classification:** Windows desktop beta candidate; hosted website private preview. BlackMarket AI is local-first market research and paper-trading software. Paper trading is the only execution mode; real-money exchange order execution is not supported or verified. The assistant is deterministic and read-only by default; the optional OpenAI-compatible provider only interprets retrieved evidence. ML training or model registration does not establish profitability or promotion without validation evidence.

Audit corrections and outstanding work:
- Root `LICENSE` exists and identifies the project as proprietary. Statements that no root license exists are outdated.
- CI run #605 passed on an earlier commit, not the current source baseline. Fresh current-head CI and release-artifact verification remain required.
- The website is a shared-password private preview, not multi-user identity or tenant isolation. Hosted backend, durable storage, streaming and restore acceptance remain release gates.
- The repository contains 30 generated compressed shutdown database backups under `data/backups/` using `.db.gz`; the current ignore rules do not exclude this suffix. Contents were not inspected. Review safely and remove generated database artifacts from version control.
- SQLite databases, model artifacts and backup archives are not application-encrypted. SHA-256 manifests provide integrity, not confidentiality.

This is source/documentation evidence only; it does not claim live deployment verification, fresh training/backtest, current-head CI, security certification or profitable performance.
