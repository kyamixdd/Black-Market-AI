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
