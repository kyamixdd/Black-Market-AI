# BlackMarket AI — Web Dashboard

This is the browser interface for the shared BlackMarket AI backend. The Tauri desktop app remains separate and continues to use its loopback-only API mode.

## Deployment environment variables

Set these in the hosting provider (never commit actual secrets):

- `BLACKMARKET_BACKEND_URL`: HTTPS origin of the private backend, without trailing slash.
- `BLACKMARKET_API_TOKEN`: same strong bearer token configured in backend `BLACKMARKET_API_TOKEN`.
- `BLACKMARKET_WEB_PASSWORD`: unique web sign-in password.
- `BLACKMARKET_SESSION_SECRET`: random secret of at least 32 characters.

The web app signs an HTTP-only, secure production cookie. The browser never receives the backend bearer token. All API requests pass through the authenticated server-side proxy.

## Backend requirements

The backend must be deployed on a trusted host with HTTPS, persistent storage, restricted inbound access, and `BLACKMARKET_REMOTE_API_ENABLED=1`. Bind with `BLACKMARKET_API_HOST=0.0.0.0` only behind the host's firewall/reverse proxy. Set `BLACKMARKET_ALLOWED_ORIGINS` to the exact website origin if browser-origin access is ever enabled; the server-side proxy itself does not need CORS.

Use a strong random `BLACKMARKET_API_TOKEN`; keep the backend port private or allow inbound only from the web host. Never expose the API token to browser code. Keep `REAL_TRADING_ENABLED=false`.

## Development

```bash
cd blackmarket-web
npm install
cp .env.example .env.local
npm run dev
```

The dashboard polls the existing REST endpoints every 15 seconds. WebSocket events are not yet proxied by this serverless web edition; use the desktop app for the existing local real-time stream until a hosted WebSocket gateway is implemented. Endpoints that are not implemented by the backend will show their API errors rather than fabricated data.

## Scope and security

The single-password gate is suitable only as an initial private preview. Before public multi-user access, add per-user identity, rate limiting, audit logs, CSRF controls for state-changing endpoints, and role-based permissions. Keep this preview behind hosting-level access controls if possible. No real-money trading is enabled by this dashboard.
