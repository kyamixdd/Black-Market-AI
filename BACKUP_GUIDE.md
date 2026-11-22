# Backup and Recovery

## Data locations

The Tauri desktop stores application data in a per-user application-data directory. The Python/terminal path may use a configured project or user data directory. The active database location is determined by the runtime configuration, including `BLACKMARKET_CONFIG_DIR` and the configured database path.

## Data included in a backup

- SQLite database and required SQLite sidecar files.
- Compressed application-created backups.
- Model artifacts and model registry data.
- Application settings and configuration.
- Relevant logs for incident diagnosis.

SQLite databases and backup archives are not encrypted by the application. Apply OS-level disk encryption and restrictive filesystem permissions.

## Automatic backup

The recovery subsystem creates verified compressed SQLite backups according to the configured schedule and during graceful shutdown. The development log records a six-hour interval and retention of up to 30 backups for the verified desktop configuration. Actual locations and retention depend on runtime configuration.

Backup completion should be confirmed from the backup timestamp and integrity result.

## Manual backup

1. Exit the application normally.
2. Confirm the managed backend process has stopped.
3. Copy the database and relevant model/configuration directories to protected storage.
4. Preserve any SQLite sidecar files present at shutdown.
5. Verify the copied database before relying on it.

For an active database, use SQLite's online backup API or the application's verified backup mechanism. A basic copy of the main database file alone may not capture a consistent transaction state.

## Backup validation

Run an integrity check against a copy:

```bash
sqlite3 path/to/backup.db "PRAGMA integrity_check;"
```

Expected output: `ok`.

An integrity check verifies database structure; application-level record completeness requires additional checks.

## Restore procedure

1. Exit the application and confirm backend shutdown.
2. Preserve a copy of the current database and sidecar files.
3. Extract the selected backup into a temporary directory.
4. Run `PRAGMA integrity_check;` against the temporary database.
5. Restore the verified database to the configured location.
6. Start the application and verify readiness, balances, positions, orders, trade history and logs.
7. Retain the original database and backup until application-level validation is complete.

Do not overwrite the only original database with an unverified backup.

## Corruption handling

- Preserve the database and sidecar files before repair attempts.
- Retain logs and the last known-good backup.
- Perform recovery against a copy.
- Avoid destructive SQL operations unless the original data has been preserved and the recovery procedure is understood.

## Model recovery

Restore model artifacts and registry metadata from a compatible backup/version. Candidate models must not be manually promoted outside the configured validation and promotion process. When a model is suspected of causing incorrect behavior, retain its artifacts and logs and use the supported rollback or disablement mechanism.

## Operational checklist

- [ ] Confirm the active database path.
- [ ] Confirm the latest automatic backup exists.
- [ ] Validate backup integrity on a copy.
- [ ] Include required models, registry, settings and logs.
- [ ] Store an encrypted or access-controlled secondary copy.
- [ ] Perform periodic restore drills using disposable data.
- [ ] Confirm restored paper-trading records are consistent and not duplicated.
