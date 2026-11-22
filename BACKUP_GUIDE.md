# BlackMarket AI — Backup and Recovery

Last reviewed: 22 November 2026

This guide covers local application data for the Tauri desktop and Python/terminal modes. The installed desktop uses a per-user application-data directory; it does not necessarily use the repository's `data/` folder. Use the app's startup diagnostics/logs and configured `BLACKMARKET_CONFIG_DIR` / database path to identify the active locations.

## What to preserve

- SQLite database and any SQLite sidecar files present while the application is running (for example, WAL/SHM files).
- Compressed application-created backups.
- Model artifacts and model registry data.
- User configuration and settings files.
- Logs needed to diagnose a failed recovery.

The database and backups are not encrypted by the application. Protect copies with OS disk encryption, filesystem permissions, and secure storage.

## Automatic backup behavior

The recovery subsystem creates verified compressed SQLite backups according to the configured backup schedule and on graceful shutdown. The development progress log records a six-hour backup interval and retention of up to 30 backups for the verified desktop configuration. Actual backup location and retention can vary with the configured application-data path; verify the current configuration and logs before relying on a schedule.

Do not assume a backup completed just because the application exited. Check the latest backup timestamp and integrity result.

## Safe manual backup

**Preferred:** close BlackMarket AI normally and confirm its backend has stopped, then copy the database and required model/configuration directories to a protected backup location.

For a database that is actively in use, do not copy only the main `.db` file with a basic file-copy command. Use SQLite's online backup API or the application's verified backup mechanism so the copy is transactionally consistent.

Keep at least one backup on a separate storage device. Do not include secrets in a cloud or shared archive unless it is encrypted and access-controlled.

## Verify a backup

Use SQLite against a copy of the backup:

```bash
sqlite3 path/to/backup.db "PRAGMA integrity_check;"
```

Expected output is `ok`. Also check that important tables can be queried and that the file corresponds to the expected application date/version. A successful integrity check alone does not prove all application-level records are correct.

## Restore procedure

1. Exit the desktop app normally.
2. Confirm the managed backend has stopped and port `127.0.0.1:8765` is no longer listening.
3. Make a separate copy of the current database and its sidecar files before changing anything.
4. Extract or copy the selected backup into a temporary directory.
5. Run `PRAGMA integrity_check;` on the temporary database.
6. Restore to the configured database location only after the backup passes verification.
7. Start the application and check backend/database readiness, portfolio balances, open positions/orders, trade history, and logs.
8. Preserve the original database and backup until the restored application has been validated.

Never delete the only original database or overwrite it with an unverified backup.

## Corruption or failed startup

If integrity validation fails:

- Stop the application and preserve the database and sidecar files.
- Copy the files before any repair attempt.
- Review the backend log and the latest known-good backup.
- Test recovery against a copy.
- If no verified backup exists, preserve the original and seek help before running destructive SQL.

Do **not** drop tables, delete the database to make startup succeed, or use a forced process kill as the first recovery step.

## Model recovery

Model artifacts and registry metadata should be restored from the same backup/version where possible. Do not manually mark a candidate model as active or bypass the current validation/promotion gate. If a model is suspected of behaving unexpectedly, disable model-driven signal execution through supported configuration, retain the artifacts and logs, and use the application's validated rollback mechanism.

## Backup checklist

- [ ] Identify the active database and application-data location.
- [ ] Verify the most recent automatic backup exists.
- [ ] Verify backup integrity on a copy.
- [ ] Preserve models, registry, settings, and logs as needed.
- [ ] Keep an encrypted/offline or otherwise access-controlled off-site copy.
- [ ] Perform a restore drill on a disposable copy periodically.
- [ ] Confirm the restored application recovers paper positions, orders, and trade history without duplication.
