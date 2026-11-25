---
name: database-engineer
description: SQLite schema, persistence, repositories, migrations, backups, and recovery.
---

# Database Engineer

SQLite is the permanent memory of BlackMarket AI.

## Required data tables
- symbols
- candles
- market_snapshots
- features
- signals
- predictions
- paper_orders
- paper_positions
- trade_history
- strategy_metrics
- model_registry
- learning_runs
- notifications
- system_events

## Requirements
- Use SQLAlchemy and aiosqlite where appropriate.
- Define explicit schemas, constraints, indexes, and relationships.
- Store timestamps consistently.
- Persist every important signal and trade lifecycle transition.
- Prevent duplicate signal and execution records.
- Keep losing trades and failed predictions in history.
- Store model versions and training metadata.
- Track expectancy, drawdown, profit factor, average win/loss, costs, and sample size.
- Implement database backups and recovery tests.
- Resolve backup storage from configured `BACKUP_DIR`; the desktop app must keep backups under its per-user data directory, never the installer working directory.
- Use transactions for balance and position changes.

The application must recover balances, open positions, model metadata, and critical event history after restart.

Desktop startup must verify SQLite integrity before starting market services. On integrity failure, report the error and preserve the database for recovery; never silently recreate or overwrite it.

Never silently discard data or fabricate historical records.

## Phase 2 recovery details
- The production orchestrator wires database-backed disaster recovery into initialization and graceful shutdown. Open positions and open/partial paper orders are rehydrated by their primary IDs; repeated recovery must not duplicate either.
- Opening positions and order placement/fill events are written to the existing paper tables. Completed trade persistence and the corresponding position closure update happen in one database transaction; retain the closed position row and trade history.
- Account baseline configuration is read from the simulator configuration during recovery; a separately persisted, user-adjustable account baseline is not currently implemented.
- Recovery does not imply active exchange-stream restoration: configured production Binance WebSocket subscriptions are currently absent.
