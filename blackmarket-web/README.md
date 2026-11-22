# BlackMarket AI — Website / Private Preview

The canonical React + TypeScript dashboard lives in `../blackmarket-desktop/src`. Both targets use that same UI:

- **Desktop:** Vite + Tauri with a supervised local backend at `127.0.0.1:8765`.
- **Website:** Next.js session/login and same-origin backend proxy; REST calls use `/api/backend` and live events use the authenticated SSE proxy.

Do not fork the dashboard into a separate website implementation.

## Status

The website is an **optional private-preview path**, not the supported public hosted product. The primary release path is the Tauri desktop application with its local backend.

The latest audited branch head is `db3fc448af100236efac42ee8ed8e2fbe6a162d7`. CI run #343 reported success. Hosted website readiness still requires deployment-specific end-to-end verification; a successful frontend build does not prove the remote API, database, event stream, market-data freshness, or trading workflow is operational.

## Website environment

Copy `.env.example` to `.env.local` and configure these server-only variables:

- `BLACKMARKET_BACKEND_URL` — HTTPS backend URL, no trailing slash.
- `BLACKMARKET_SESSION_SECRET` — high-entropy random secret, at least 32 characters.
- `BLACKMARKET_WEB_PASSWORD` — strong private-preview password.
- `BLACKMARKET_API_TOKEN` — high-entropy bearer token shared with the backend.

Never expose the session secret, preview password, or backend token to browser code or public build-time variables.

## Backend requirements for remote preview

Set on the backend host:

- `BLACKMARKET_REMOTE_API_ENABLED=1`
- `BLACKMARKET_API_HOST=0.0.0.0` (only if required by the platform)
- `BLACKMARKET_API_TOKEN` to the same secret configured on the website
- `APP_ENV=production`
- A durable database path/volume and appropriate backup configuration
- Allowed origins and ingress restrictions appropriate to the deployed website

Remote API mode is disabled by default. Use TLS and restrict backend ingress to the website host or gateway where possible. Do not expose the backend directly without reviewing its threat model.

## Setup and build

Requirements: Node.js 20+ (use the repository's supported CI Node version when building).

```bash
cp .env.example .env.local
npm install
npm run build
npm start
```

Deploy the Next.js app as a Node.js service. The deployment must include `blackmarket-desktop`, because the website imports the shared frontend source from that directory.

## Authentication limitations

The current website gate is a single-password private-preview session, not multi-user identity, roles, MFA, or account recovery. Do not use it as a public customer authentication system.

See the root [SECURITY.md](../SECURITY.md) and [RELEASE_READINESS.md](../RELEASE_READINESS.md) for security and release requirements.
