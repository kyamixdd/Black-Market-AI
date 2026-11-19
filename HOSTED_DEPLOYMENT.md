# Hosted BlackMarket AI deployment

The desktop and website use the same Python orchestrator, database repositories, settings, learning cycle, and market-data pipeline. The desktop supervisor starts the backend locally; the Render website service starts the same backend beside Next.js and proxies authenticated requests through the Next.js session.

## Required Render environment

Set these values on the existing `blackmarket-ai-web` service:

- `BLACKMARKET_API_TOKEN`: a new random secret of at least 32 bytes. Keep it private; the browser never receives it.
- `BLACKMARKET_WEB_PASSWORD`: the website login password.
- `DATABASE_URL`: a durable PostgreSQL connection URL. The backend accepts `postgresql://` or Render's `postgres://` URL and uses psycopg 3.
- `BLACKMARKET_SESSION_SECRET`: retain the generated Render secret.
- `BLACKMARKET_BACKEND_URL`: `http://127.0.0.1:8765` (set by the Blueprint).

The Blueprint sets `APP_ENV=production`, enables remote API mode only for the loopback Node-to-Python connection, and starts the Python API on loopback. Do not expose port 8765 publicly. The Next.js proxy requires the authenticated website session and attaches the private backend bearer token server-side.

## Persistent storage requirements

Hosted production deliberately refuses SQLite because Render's ordinary service filesystem is ephemeral. Use a managed PostgreSQL database and configure its connection URL above. PostgreSQL backups must be enabled at the database provider; the desktop SQLite backup manager is not used for PostgreSQL.

Model artifacts are still written to `MODELS_DIR` / `BLACKMARKET_MODELS_DIR`. For durable hosted model training, mount persistent storage and point `BLACKMARKET_MODELS_DIR` to it, or use a durable model-artifact store before enabling automatic model promotion. The current learning cycle deliberately keeps new candidates inactive until cost-aware champion/challenger evaluation is integrated.

## Safety

- `REAL_TRADING_ENABLED=true` is rejected by startup validation.
- Exchange clients are public market-data clients; the backend does not expose order-placement endpoints.
- Desktop defaults to a local SQLite database; the hosted website uses PostgreSQL. Settings and virtual balances synchronize across desktop and website only when both are configured to use the same PostgreSQL DATABASE_URL. Keep that URL private and use a secure connection.
- Changes to market enablement, scan-all, timeframes, and Telegram enablement are persisted and reported as restart-required. Risk limits and virtual capital changes apply immediately; virtual capital cannot be changed while positions or orders are open.

## Before deploying

1. Create or select a durable PostgreSQL database and set `DATABASE_URL`.
2. Set `BLACKMARKET_API_TOKEN` and `BLACKMARKET_WEB_PASSWORD` in Render's private environment settings.
3. If automatic model training is required on the hosted service, configure durable model-artifact storage before relying on trained models across deploys.
4. Review GitHub Actions. Do not deploy until all four checks pass.
5. Verify the Render deployment, `/health`, authenticated login, market data, settings persistence, and browser event stream.

The free Render web tier can sleep and has constrained memory/CPU. It is suitable for initial integration checks, not a guarantee of uninterrupted market scanning or production trading uptime. Keep real-money execution disabled.
