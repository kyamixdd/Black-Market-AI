# BlackMarket AI — shared frontend deployment

The canonical React + TypeScript application lives in `../blackmarket-desktop/src`. Both deployment targets mount that exact source:

- **Desktop:** Vite + Tauri, using the supervised local Python API at `127.0.0.1:8765`.
- **Website:** Next.js authentication/session and same-origin API proxy shell; it imports the canonical React application directly. Browser REST requests use `/api/backend`, and live updates use the authenticated SSE proxy.

There is one dashboard implementation. Do not create a separate website dashboard.

## Website setup

1. Use Node.js 20+.
2. Copy `.env.example` to `.env.local`.
3. Configure `BLACKMARKET_BACKEND_URL`, `BLACKMARKET_SESSION_SECRET` (32+ random characters), `BLACKMARKET_WEB_PASSWORD`, and `BLACKMARKET_API_TOKEN`.
4. Run `npm install`, `npm run build`, then `npm start`.
5. Deploy the Next.js app as a Node.js service. Ensure the deployment includes the repository's `blackmarket-desktop` directory because the website imports the canonical UI from there.

The backend host must run with:
- `BLACKMARKET_REMOTE_API_ENABLED=1`
- `BLACKMARKET_API_HOST=0.0.0.0`
- `BLACKMARKET_API_TOKEN` set to the same high-entropy bearer token configured as `BLACKMARKET_API_TOKEN` on the website
- `APP_ENV=production` and a durable database configuration appropriate to the host

Remote API mode is disabled by default. When enabled, all `/api/*` requests still require the bearer token. Do not expose that token to browser JavaScript. Prefer restricting backend ingress to the website host where the platform supports it.

## Desktop setup

Use the existing `blackmarket-desktop` Vite/Tauri instructions. Desktop startup and its loopback-only API remain the default when remote mode is disabled.

## Security and scope

The website login is a single-password private-preview gate, not multi-user identity or role-based access. Use HTTPS, rotate secrets, and do not enable real-money order execution as part of this frontend consolidation. Paper trading remains the application scope.
