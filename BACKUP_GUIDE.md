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


## Stage 10 implementation notes

- A manual backup can be triggered through the authenticated API: `POST /api/backup/create` with JSON `{"description":"before-upgrade"}`. The response includes the managed filename and manifest. `GET /api/backup/list` lists managed backup filenames and metadata; it does not expose arbitrary filesystem paths.
- Backups use SQLite's online backup API. The manager validates the database and writes a paired `.json` manifest containing format version, UTC creation time, description, backup filename, size, SHA-256 checksum, compression state, and integrity result.
- Restore validates archive readability, SQLite `PRAGMA integrity_check`, manifest filename, checksum, and size before replacing the target. Invalid or missing backups are rejected without replacing the target. Live database restore checkpoints WAL, disposes the engine, replaces the file atomically, and reinitializes the database.
- Backup retention counts backup files (not manifests) and removes the corresponding manifest together. Filename descriptions are sanitized and timestamps include microseconds to avoid collisions.
- Database initialization performs a SQLite `quick_check` on an existing non-empty database before schema creation. Additive paper-trading migrations are idempotent and recorded in `schema_migrations` (version 2; version 1 covers paper-trading recovery columns, version 2 adds saved strategy definitions, backtest reports, and workspace snapshots). Use `Database.integrity_check()` and `Database.foreign_key_check()` for diagnostics.
- Runtime settings and risk configuration are persisted in `runtime_settings.json` using atomic replacement and restrictive permissions where supported. Each new backup includes a validated settings sidecar (`.settings.json`) with a checksum and size in its manifest; restore stages and validates settings together with the database and attempts database rollback if the restore fails. Environment `.env` secrets are not included. Dashboard preferences are saved in workspace snapshots.
- Dedicated SQLite tables persist saved strategy definitions (`saved_strategies`), immutable Strategy Lab and comparison reports (`backtest_reports`), and dashboard workspace snapshots (`workspaces`). Strategy Lab runs and comparisons are automatically stored before the result is returned. The Strategy Lab UI supports saving/loading strategy definitions, opening saved reports, saving workspace snapshots, and restoring a snapshot into the dashboard.
- Paper account balances are reconstructed from configured initial balances, durable completed trades, open positions, reserved funds, and fees during recovery. Open positions and recoverable orders are loaded from SQLite.

### Restore drill (desktop/backend stopped)

1. Create a manual backup and save the returned filename.
2. Stop the application and confirm the managed backend has exited.
3. Preserve the current database file and any `-wal` / `-shm` files.
4. Use the application's `DatabaseBackupManager.restore_backup(Path(BACKUP_DIR) / filename)` from a trusted local maintenance script. Do not pass a path outside the configured backup directory.
5. Start the app and verify paper balances, open positions/orders, trade history, risk settings, runtime settings, saved strategy definitions, backtest reports, workspaces, and saved dashboard preferences.
6. Keep the pre-restore database until these checks succeed.

Restore is intentionally not exposed as an arbitrary-path HTTP endpoint. It requires the application to be stopped or coordinated so no active process can write while the database is replaced.
