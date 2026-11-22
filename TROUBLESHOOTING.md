# BlackMarket AI — Troubleshooting

Last reviewed: 22 November 2026

## Choose the correct run mode

- **Tauri desktop:** primary product path; the desktop supervisor starts and manages the local backend.
- **Vite browser preview:** frontend-only; it does not supervise the Python backend.
- **Next.js website:** private-preview path; requires server-side session and remote-backend configuration.
- **Python/terminal mode:** legacy/local development entry point.

A successful frontend page load does not prove the backend or market data is ready.

## Desktop startup or backend unavailable

1. Launch the desktop app normally and wait for the readiness checks.
2. Use the startup screen's diagnostic/log location.
3. Confirm the app has permission to use its per-user application-data directory.
4. Check that another BlackMarket AI instance is not already using port `127.0.0.1:8765`.
5. Confirm the bundled backend resources exist in the installed application.
6. If startup still fails, preserve the backend log and exact app version before reinstalling.

The current Windows installer pipeline packages a backend executable. Older development builds may require a configured Python environment; follow the instructions for the exact build rather than assuming all releases have identical packaging.

## API authentication errors

- A `401 Unauthorized` response means the local API bearer token is missing or invalid.
- A `403 Remote API access is disabled` response means the request is not loopback and remote mode is off.
- Do not paste or send the bearer token in screenshots, issues, or logs.
- Do not enable remote mode merely to fix a local desktop connection.

## Market data missing, delayed, or stale

- Check the backend/database/WebSocket readiness indicators.
- Check internet connectivity and whether Binance public endpoints are reachable.
- Check the selected market (Spot/Futures), symbol, and timeframe.
- Historical analytics may show unavailable until sufficient candles have been collected.
- Binance rate limits or service interruptions can delay updates. Wait for retries and inspect logs.
- Do not treat stale snapshots or missing metrics as valid live values.

## Website private-preview connection

The website uses a server-side proxy. Verify the deployment has the correct server-only values for backend URL, session secret, preview password, and backend API token. Confirm the backend has remote API mode enabled only when intended, TLS is configured, the bearer token matches, and the host's ingress permits the website service.

Never put the backend token in client-side JavaScript or public build variables. The website's single-password gate is for private preview, not a multi-user account system.

## Paper orders rejected

Read the backend rejection reason. Common causes include invalid symbol/market/side, invalid price or quantity, insufficient simulated balance, position count/exposure limits, leverage limits, stale market data, or daily loss protection.

Use smaller valid paper quantities and verify the active risk settings. Do not weaken risk controls simply to make a test order pass.

## Database locked, corrupted, or recovery failed

1. Close the app normally and ensure its managed backend stopped.
2. Preserve the database and SQLite sidecar files.
3. Check the log and configured database path.
4. Verify a backup on a copy using `PRAGMA integrity_check;`.
5. Restore only after the copy passes integrity validation.

Do not delete the database, drop tables, or force-kill all Python processes as a routine fix. A forced kill can affect unrelated applications and may leave data in an uncertain state.

## Windows installer or update issues

- Confirm the installer is from the intended release and check its version/hash.
- Install on a supported Windows version with required WebView2/system components.
- If startup fails, collect the app version and backend log before uninstalling.
- Back up user data before reinstalling or changing versions.
- After uninstall, verify the app process/backend has stopped. User data may intentionally remain to protect paper-trading history.

## Python/terminal development issues

For the Python CLI path, use Python 3.10+, activate the intended virtual environment, and install the requirements for the backend. Run tests with:

```bash
python -m pytest -q -m "not live"
```

Do not use a different interpreter than the one where dependencies were installed.

## Learning/model promotion issues

Model training or promotion may be blocked when the dataset is too small, timestamps are invalid, chronological/purged validation is insufficient, confidence calibration lacks samples, or economic/champion evidence is incomplete. This fail-closed behavior is intentional. Do not reduce promotion thresholds to bypass release or safety checks.

## Reporting a bug

Include:
- app version and commit/branch,
- Windows/OS version and run mode,
- relevant redacted logs,
- exact steps and expected/actual behavior,
- whether the issue is reproducible.

Remove bearer tokens, website secrets, Telegram tokens, private database content, and personal paths before sharing.
