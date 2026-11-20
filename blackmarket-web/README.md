# BlackMarket AI — shared frontend deployment

The canonical React + TypeScript application lives in `../blackmarket-desktop/src`.
Both deployment targets mount that same source:

- Desktop: Vite + Tauri, using the supervised local Python API at `127.0.0.1:8765`.
- Website: Next.js shell for login/session security and same-origin API proxying; it imports the canonical React application directly. Browser API requests use `/api/backend`, and browser live updates use the authenticated SSE proxy.

There is no second website dashboard implementation.

## Website setup

1. Install Node.js 20+.
2. Copy `.env.example` to `.env.local`.
3. Configure `BLACKMARKET_BACKEND_URL`, `BLACKMARKET_SESSION_SECRET` (32+ random characters), `BLACKMARKET_WEB_PASSWORD`, and `BLACKMARKET_API_TOKEN`.
4. Run `npm install`.
5. Run `npm run build`, then `npm start`.

Deploy this Next.js app as a Node.js service. The backend must be reachable over HTTPS from the website server. Do not expose the backend bearer token to browser JavaScript.

## Desktop setup

Use the existing `blackmarket-desktop` Vite/Tauri instructions. Desktop startup and its local supervisor remain unchanged.

## Security notes

The website login remains a single-password private-preview gate, not multi-user identity or role-based access. Use HTTPS, rotate secrets, restrict backend network access to the web host where possible, and do not enable real-money order execution as part of this frontend consolidation.
