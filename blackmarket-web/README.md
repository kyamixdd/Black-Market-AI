# BlackMarket AI — Website / Private Preview

The canonical React + TypeScript dashboard lives in `../blackmarket-desktop/src`. Both targets use that same UI:

- **Desktop:** Vite + Tauri with a supervised local backend at `127.0.0.1:8765`.
- **Website:** Next.js session/login and same-origin backend proxy; REST calls use `/api/backend` and live events use the authenticated SSE proxy.

Dashboard changes are maintained in the canonical shared source tree.

## Status

The website is an **optional private-preview path**, not the supported public hosted product. The primary release path is the Tauri desktop application with its local backend.

Audit status: reviewed locally on 23 November 2026. This workspace has no source commits, so prior audit hashes and CI references cannot be verified against the current files. The hosted path remains private preview.

## Website environment

Copy `.env.example` to `.env.local` and configure these server-only variables:

- `BLACKMARKET_BACKEND_URL` — HTTPS backend URL, no trailing slash.
- `BLACKMARKET_SESSION_SECRET` — high-entropy random secret, at least 32 characters.
- `BLACKMARKET_WEB_PASSWORD_HASH` — scrypt hash (never plaintext); generate locally using the script below.
- `BLACKMARKET_API_TOKEN` — high-entropy bearer token shared with the backend.

Session secrets, password hashes, and backend tokens must remain server-side and must not be included in client bundles or public build variables. The hosted preview uses a single shared password and does not provide individual user identity or user-owned data isolation.

## Hosted authentication setup

Generate a high-entropy session secret locally, and generate the password hash without writing the plaintext password to a file:

```bash
# Linux/macOS shell
export PREVIEW_PASSWORD='your-long-unique-password'
node scripts/hash-preview-password.mjs
unset PREVIEW_PASSWORD
```

Store the resulting hash in `BLACKMARKET_WEB_PASSWORD_HASH` and the random session secret in `BLACKMARKET_SESSION_SECRET`. Hosted sessions are signed, HttpOnly, SameSite=Strict cookies with a 30-minute expiry. Logout revokes the session in the current Node process and clears the cookie. Revocation is process-local; on multi-instance or serverless deployments, a session issued on one instance may not be revoked on another until expiry. Rotating the session secret invalidates all sessions.

The login and proxy rate limits are also process-local and reset on restart. Configure platform-level protection for any internet-accessible preview.

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

This workspace has no `package-lock.json`; dependency resolution is not reproducible across installs until a reviewed lockfile is added and committed.

```bash
cp .env.example .env.local
npm install
npm run build
npm start
```

Deploy the Next.js app as a Node.js service. The deployment must include `blackmarket-desktop`, because the website imports the shared frontend source from that directory.

## Authentication limitations

The current website gate is a single-password private-preview session, not multi-user identity, roles, MFA, or account recovery. The current authentication model is limited to private preview use.

All authenticated website sessions currently use the configured shared backend. Per-user portfolios, positions, trading history, risk settings and workspaces are not isolated. Do not expose this deployment as a multi-user product.

See the root [SECURITY.md](../SECURITY.md) and [RELEASE_READINESS.md](../RELEASE_READINESS.md) for security and release requirements.
