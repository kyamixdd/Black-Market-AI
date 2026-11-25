# Troubleshooting

## Runtime modes

| Mode | Backend behavior |
|---|---|
| Tauri desktop | Desktop supervisor starts and manages the local backend |
| Vite browser preview | Frontend only; does not supervise the Python backend |
| Python/terminal | Local development and legacy CLI path |

Frontend availability does not indicate backend readiness or current market-data availability.

The health summary reports component readiness separately. A `DEGRADED` status can mean the backend and market feeds are running but no validated model is available; automated paper entries remain gated until model validation passes.

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
- USDⓈ-M delivery-contract symbols can contain a date suffix such as `BTCUSDT_261225`; current active contracts are eligible and their candles must pass the same closed-candle and freshness checks as perpetuals.
- `stale_latest_candle` or `empty_response` means the refresh was not accepted; the scanner backs off rather than repeatedly requesting the same failing timeframe. Spot and Futures periodically synchronize freshness checks with their own `/time` endpoint. A logged clock offset corrects the comparison but does not bypass the stale-data guard.
- Compare the latest kline close time with the matching exchange `/time` response, not only the HTTP `Date` header. A close time later than now can be the current, still-open candle; it is excluded until complete. If exchange time and klines are themselves delayed, wait for the public feed to recover rather than overriding the freshness check.
- `Connecting WS` is only an attempt. Look for recent messages for both markets in the health snapshot; a connected socket with no received events is stale. Spot ticker data uses `@ticker`; Futures price updates use the live best-bid/ask midpoint while REST supplies 24-hour volume and change.

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

Use Python 3.12+ and the virtual environment associated with the backend dependencies. The installer build expects Python 3.12 on the build machine. Check the installed interpreter before creating the project virtual environment; do not replace or modify a global Python installation.

```bash
python -m pytest -q -m "not live"
```

The command must run under the intended Python interpreter.

## Model training or promotion blocked

`active_trained_model_unavailable` means automated paper entries are being held because there is no usable trained model. Check the Learning status for its bootstrap/retraining state and last-cycle reason. New models remain inactive candidates until timestamped walk-forward validation, calibration, cost-adjusted economic evidence and champion checks pass; do not lower these safeguards to force activation. After a validated promotion, confidence calibration still needs resolved outcomes for that exact model version before automated entries become ready.

Promotion may be rejected because of insufficient samples, invalid timestamps, inadequate chronological/purged validation, insufficient calibration samples, or incomplete economic/champion evidence. These conditions are validation gates; reducing thresholds to bypass them invalidates the evidence. A failed training or promotion should leave the existing active model in place.

## Bug report contents

Include application version/commit, OS version, runtime mode, redacted logs, reproduction steps, expected behavior and actual behavior.

Exclude bearer tokens, Telegram tokens, private database contents and personal filesystem paths.
