"""Test database persistence and repositories."""
from datetime import datetime, timezone

from database.connection import Database
from database.repositories import Repository


def test_database_init(tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_file}")
    db.init_db()
    health = db.health()
    assert health["status"] == "ok"
    assert health["tables"] > 0
    assert db.integrity_check() == "ok"



def test_database_initialization_and_additive_migration_are_idempotent(tmp_path):
    import sqlite3

    db_file = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_file)
    connection.execute("CREATE TABLE paper_positions (position_id VARCHAR(64) PRIMARY KEY)")
    connection.execute("CREATE TABLE trade_history (id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    db = Database(f"sqlite:///{db_file}")
    db.init_db()
    db.init_db()
    with db.engine.connect() as connection:
        position_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(paper_positions)")}
        trade_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(trade_history)")}
    assert {"reserved_notional", "reserved_margin", "order_id", "strategy"} <= position_columns
    assert "order_id" in trade_columns
    assert db.integrity_check() == "ok"
    assert db.foreign_key_check() == []
    with db.engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version FROM schema_migrations"
        ).scalar_one() == 1
    db.close()


def test_corrupt_sqlite_database_is_detected_before_init(tmp_path):
    db_file = tmp_path / "corrupt.db"
    db_file.write_bytes(b"not a sqlite database")
    db = Database(f"sqlite:///{db_file}")
    import pytest
    with pytest.raises(RuntimeError, match="integrity check|could not be opened"):
        db.init_db()
    db.close()

def test_symbol_repository(tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_file}")
    db.init_db()
    repo = Repository(db.session_maker())

    symbols = [
        {
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "price_precision": 2,
            "quantity_precision": 5,
            "tick_size": 0.01,
            "step_size": 0.00001,
            "min_notional": 10.0,
            "status": "TRADING",
            "is_eligible": True,
        }
    ]
    saved = repo.save_symbols(symbols)
    assert saved == 1

    eligible = repo.get_eligible_symbols("SPOT")
    assert len(eligible) == 1
    assert eligible[0].symbol == "BTCUSDT"


def test_recent_market_snapshots_are_returned_newest_first_with_limit(tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_file}")
    db.init_db()
    repo = Repository(db.session_maker())
    timestamps = [
        datetime(2025, 1, 1, hour, tzinfo=timezone.utc)
        for hour in (1, 2, 3)
    ]
    snapshot_ids = [
        repo.save_snapshot({
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "timestamp": timestamp,
            "price": 100.0 + index,
            "volume_24h": 1_000.0,
            "price_change_24h": 1.0,
        })
        for index, timestamp in enumerate(timestamps)
    ]

    recent = repo.get_recent_snapshots(limit=2)

    assert [snapshot.id for snapshot in recent] == snapshot_ids[-2:][::-1]


def test_closed_trade_history_is_persisted_without_duplicates(tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(f"sqlite:///{db_file}")
    db.init_db()
    repo = Repository(db.session_maker())
    opened_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    closed_at = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    trade = {
        "position_id": "paper-position-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "BUY",
        "entry_price": 100.0,
        "exit_price": 102.0,
        "amount": 0.1,
        "leverage": 1.0,
        "pnl": 0.19,
        "pnl_pct": 1.9,
        "fee": 0.01,
        "strategy": "TEST",
        "opened_at": opened_at,
        "closed_at": closed_at,
        "close_reason": "TAKE_PROFIT",
    }

    repo.save_trade_history(trade)
    repo.save_trade_history({**trade, "pnl": 0.18})

    history = repo.get_trade_history()
    assert len(history) == 1
    assert history[0].position_id == trade["position_id"]
    assert history[0].pnl == 0.18
