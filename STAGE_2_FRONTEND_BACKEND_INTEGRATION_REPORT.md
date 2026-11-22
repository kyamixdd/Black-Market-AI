# Stage 2 — Frontend and Backend Integration

## Scope

Centralize frontend transport selection and make desktop, hosted, and Vite development transports explicit. Preserve the desktop's local Python engine and use the hosted Next.js server as a credential-holding proxy to a separately deployed FastAPI backend.

## Changes

- `blackmarket-desktop/src/services/backendClient.ts`: central runtime selection; Tauri uses `http://127.0.0.1:8765/api`, browser uses same-origin `/api/backend`. Added central event-stream and WebSocket URL selection, bounded timeout and safe GET/HEAD retries, actionable errors, and health helper. Mutations are not retried.
- `blackmarket-desktop/src/App.tsx`: startup health and authenticated system-status checks derive endpoints from shared configuration.
- `blackmarket-desktop/src/services/websocket.ts`: shared runtime URL selection; hosted browser uses same-origin SSE, desktop uses authenticated local WebSocket.
- Added transport selection, timeout, bounded retry and hosted SSE reconnect tests.
- `blackmarket-desktop/vite.config.ts` and root `.env.example`: configurable development target via `VITE_BACKEND_PROXY_TARGET` (URL only, never a secret); Vite rewrites browser proxy paths to backend routes.
- `blackmarket-web/app/api/backend/[...path]/route.ts`: bounded upstream request timeouts while preserving cancellation and server-side bearer forwarding.

## Transport boundaries

| Runtime | REST | Health | Realtime |
|---|---|---|---|
| Tauri desktop | Local loopback API with native bearer token | Local `/health` | Authenticated local WebSocket |
| Hosted browser | Same-origin `/api/backend` | Same-origin `/api/health` | Same-origin authenticated SSE |
| Vite development browser | Same-origin proxy to configurable backend | Proxy to backend `/health` | SSE proxy; local WebSocket remains for Tauri |

Hosted backend credentials remain in Next.js server environment variables (`BLACKMARKET_API_TOKEN`). No backend bearer token is added to Vite client variables or browser bundles.

## Deployment configuration

Hosted web requires server-side `BLACKMARKET_BACKEND_URL` (HTTPS URL without trailing slash) and `BLACKMARKET_API_TOKEN`, plus existing website session configuration. FastAPI must be deployed separately on a persistent backend host with remote API mode explicitly enabled, strong bearer token, allowed website origin configuration, and persistent storage. Vercel remains the frontend/proxy, not the persistent Python engine or hosted WebSocket server.

Hosted realtime intentionally uses SSE through the Next.js proxy because the backend `/ws` endpoint is loopback-only and the hosted proxy does not implement WebSocket tunneling.

## Validation status

Automated tests were added for transport selection, timeout, safe-request retries, desktop WebSocket reconnect (existing), and hosted SSE reconnect. This branch has not yet been validated by a completed CI run or end-to-end hosted backend connection. Hosted connectivity requires the backend service and server environment variables to be configured and reachable. A successful Next.js build alone does not prove backend readiness.
