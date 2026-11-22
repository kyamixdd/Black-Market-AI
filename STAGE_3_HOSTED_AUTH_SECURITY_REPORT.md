# Stage 3 — Hosted Authentication and Security Hardening

## Status

Hosted private-preview authentication hardening is implemented on `stage-3/hosted-auth-security-hardening`. The change does not convert the website into a multi-user application. User-data isolation is not implemented and remains an acceptance blocker for any public or multi-user hosted release.

## Implemented

- Replaced plaintext website password comparison with a server-side scrypt password hash (`BLACKMARKET_WEB_PASSWORD_HASH`). Password hashes use random salt and constant-time comparison. A local hash-generation utility is provided; no production secret is generated or committed.
- Signed sessions now expire after 30 minutes and use a bounded process-local revocation registry. Logout revokes the current session in the active process and clears the cookie.
- Session cookie is HttpOnly, SameSite=Strict, host-only, Secure in production, and scoped to `/`.
- Login enforces same-origin requests, an 8 KiB request-body limit, and process-local brute-force throttling.
- Hosted proxy enforces same-origin state-changing requests, session authentication, a 1 MiB request-body limit, 15-second upstream timeout, bounded response size, and sanitized upstream 5xx errors.
- Rate-limit buckets are bounded and key generation uses the nearest forwarded address where available.
- Hosted public health response no longer returns the full backend health object.
- Remote FastAPI mode now requires a bearer token of at least 32 bytes; loopback-only default binding remains enforced when remote mode is disabled.
- Added automated tests for session expiration/signature/revocation, scrypt verification, rate-limit enforcement, same-origin CSRF validation, and remote API bind/token requirements. Existing backend tests already cover invalid REST tokens, CORS, and WebSocket authentication rejection.

## Environment migration

Set `BLACKMARKET_WEB_PASSWORD_HASH` instead of the removed plaintext `BLACKMARKET_WEB_PASSWORD`. Generate it locally:

```bash
cd blackmarket-web
export PREVIEW_PASSWORD='a-long-unique-password'
node scripts/hash-preview-password.mjs
unset PREVIEW_PASSWORD
```

Set the printed hash in the hosting provider's server-only environment configuration. Generate a high-entropy `BLACKMARKET_SESSION_SECRET` of at least 32 bytes and keep `BLACKMARKET_API_TOKEN` server-side. Never commit any of these values.

## Verified security boundaries and limitations

- Desktop local bearer authentication, loopback binding, and authenticated WebSocket behavior remain separate from the website session mechanism.
- Hosted authentication is still one shared password. There are no individual user identities, roles, or ownership checks.
- Hosted paper-trading data is shared by the configured backend. Portfolio, positions, trades, settings, strategies, and workspaces are not isolated by user. This does not satisfy the user-isolation acceptance criterion.
- Session revocation and rate limits are process-local. They are not durable or shared across serverless/multiple instances; a revoked session may remain valid on another instance until expiry. Use one stable instance or add shared persistence/gateway controls before public exposure.
- Tests are added but require CI to confirm the TypeScript build and runtime test suite. No hosted endpoint or production deployment was accessed or changed.

## Release gate

Do not market or deploy the hosted preview as a multi-user service until persistent user identity, per-user authorization/data partitioning, durable session revocation, shared rate limiting, and cross-user isolation tests are implemented and reviewed.
