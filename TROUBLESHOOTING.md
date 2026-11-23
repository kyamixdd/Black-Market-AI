# Troubleshooting

## Runtime modes

| Mode | Backend behavior |
|---|---|
| Tauri desktop | Desktop supervisor starts and manages the local backend |
| Vite browser preview | Frontend only; does not supervise the Python backend |
| Next.js website | Private-preview session and remote-backend configuration required |
| Python/terminal | Local development and legacy CLI path |

Frontend availability does not indicate backend readiness or current market-data availability.

## Desktop startup / backend unavailable

1. Check the startup readiness state and application logs.
2. Verify access to the per-user application-data directory.
3. Check whether another instance is using `127.0.0.1:8765`.
4. Verify bundled backend resources are present in the installed package.
5. Record the application version and backend log if startup fails.

The current Windows installer pipeline packages a backend executable. Older development builds may depend on a configured Python environment.

## API authentication

- `401 Unauthorized`: bearer token is missing or invalid.
- `403 Remote API access is disabled`: request originated outside the permitted local interface while remote mode is disabled.

Do not include bearer tokens in logs, screenshots or issue reports. Remote mode should not be enabled to resolve a local desktop authentication problem.

## Missing or stale market data

- Check backend, database and WebSocket readiness.
- Verify internet connectivity and Binance public endpoint availability.
- Confirm market, symbol and timeframe selection.
- Analytics requiring historical candles may remain unavailable until sufficient data is collected.
- Exchange rate limits and service interruptions can delay updates.
- Stale or incomplete data must not be treated as a current signal.

## Website private-preview connection

Verify server-side configuration for backend URL, session secret, preview password and backend API token. Confirm remote API mode is enabled only when required, TLS is active, tokens match, and ingress permits the website service.

Backend credentials must not be exposed in client-side code or public build variables. The current website authentication model is a single-password private-preview gate.

## Paper order rejection

Inspect the API rejection reason. Common causes include invalid symbol/market/side, invalid price or quantity, insufficient simulated balance, exposure/position limits, leverage limits, stale market data or daily-loss protection.

Order rejections caused by risk limits are expected control behavior.

## Database lock, corruption or recovery failure

1. Close the application normally and confirm backend shutdown.
2. Preserve the database and SQLite sidecar files.
3. Identify the configured database path and inspect logs.
4. Validate a backup copy using `PRAGMA integrity_check;`.
5. Restore only from a verified backup.

Deleting the database, dropping tables or terminating unrelated Python processes is not a routine recovery procedure.

## Installer or update issues

- Verify installer version and artifact hash.
- Confirm supported Windows version and required WebView2/system components.
- Preserve application logs and version information before reinstalling.
- Back up user data before upgrade/reinstall.
- Verify backend shutdown after uninstall. User data may remain intentionally to preserve trading history.

## Python/terminal environment

Use Python 3.10+ and the virtual environment associated with the installed backend dependencies.

```bash
python -m pytest -q -m "not live"
```

The command must run under the intended Python interpreter.

## Model training or promotion blocked

Promotion may be rejected because of insufficient samples, invalid timestamps, inadequate chronological/purged validation, insufficient calibration samples, or incomplete economic/champion evidence. These conditions are validation gates; reducing thresholds to bypass them invalidates the evidence.

## Bug report contents

Include application version/commit, OS version, runtime mode, redacted logs, reproduction steps, expected behavior and actual behavior.

Exclude bearer tokens, website secrets, Telegram tokens, private database contents and personal filesystem paths.


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
