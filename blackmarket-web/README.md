# BlackMarket AI — Website / Private Preview

The canonical React + TypeScript dashboard lives in `../blackmarket-desktop/src`. Both targets use that same UI:

- **Desktop:** Vite + Tauri with a supervised local backend at `127.0.0.1:8765`.
- **Website:** Next.js session/login and same-origin backend proxy; REST calls use `/api/backend` and live events use the authenticated SSE proxy.

Dashboard changes are maintained in the canonical shared source tree.

## Status

The website is an **optional private-preview path**, not the supported public hosted product. The primary release path is the Tauri desktop application with its local backend.

Audit snapshot: `db3fc448af100236efac42ee8ed8e2fbe6a162d7`. CI run #343 completed successfully for that snapshot. Deployment acceptance requires end-to-end checks for the remote API, database persistence, event stream, market-data freshness, and paper-trading workflows.

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

```bash
cp .env.example .env.local
npm install
npm run build
npm start
```

Deploy the Next.js app as a Node.js service. The deployment must include `blackmarket-desktop`, because the website imports the shared frontend source from that directory.

## Authentication limitations

The current website gate is a single-password private-preview session, not multi-user identity, roles, MFA, or account recovery. The current authentication model is limited to private preview use.

See the root [SECURITY.md](../SECURITY.md) and [RELEASE_READINESS.md](../RELEASE_READINESS.md) for security and release requirements.


## Current repository status — 23 November 2026

This document is maintained against the `black-market-ai-beta` branch. The latest application-source baseline reviewed for the comprehensive product audit is `49e6841215303ed296ced4fc1ef3039b9959426d`. Subsequent commits in this branch update documentation only; verify the branch head before treating this snapshot as current runtime or CI evidence.

Current product classification: **Windows desktop beta candidate; hosted website private preview**. The application is local-first market research and paper-trading software. Paper trading is the only execution mode; no real-money exchange order execution is supported or verified. The deterministic assistant is read-only by default; an optional OpenAI-compatible endpoint may provide interpretation. ML training and model registration do not establish profitability or promotion without the configured validation evidence.

Current audit corrections and outstanding items:
- A root `LICENSE` file exists and identifies the project as proprietary. Older statements that the root license is absent are stale.
- Existing CI run #605 passed for an earlier source commit, not the current source baseline. Fresh current-head CI and release-artifact verification remain required.
- The website is a private preview with a shared-password session gate, not a multi-user SaaS identity and isolation system. Hosted backend, durable storage, streaming and restore acceptance remain release gates.
- The repository tree contains 30 generated compressed shutdown database backups under `data/backups/` with the `.db.gz` suffix. The current ignore rules do not exclude that suffix. Their contents were not inspected in this audit; review them safely and remove generated database artifacts from version control after confirming data-handling requirements.
- The application does not encrypt SQLite databases, model artifacts or backup archives. SHA-256 manifests provide integrity checking, not confidentiality.

This status block records source/documentation evidence only. It does not claim a live deployment test, fresh training run, new backtest, current-head CI pass, security certification or trading performance result.
