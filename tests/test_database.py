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


def test_repository_persists_simulator_records_with_runtime_only_fields(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'simulator-records.db'}")
    db.init_db()
    repo = Repository(db.session_maker())

    repo.save_position({
        "position_id": "POS-RUNTIME-1",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "side": "LONG",
        "entry_price": 100.0,
        "amount": 0.1,
        "current_price": 101.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "leverage": 5.0,
        "unrealized_pnl": 0.5,
        "realized_pnl": 0.0,
        "fees_paid": 0.1,
        "status": "OPEN",
        "opened_at": datetime.now(timezone.utc),
        "margin": 10.0,
        "last_funding_time": 123456789,
        "order_type": "LIMIT",
        "signal_id": "SIG-RUNTIME-1",
        "strategy": "momentum",
    })
    repo.save_order({
        "order_id": "ORD-RUNTIME-1",
        "signal_id": "SIG-RUNTIME-1",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "order_type": "LIMIT",
        "side": "LONG",
        "amount": 0.1,
        "price": 100.0,
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc),
        "strategy": "momentum",
    })

    assert repo.get_open_positions("FUTURES")[0].position_id == "POS-RUNTIME-1"
    assert repo.get_open_orders("FUTURES")[0].order_id == "ORD-RUNTIME-1"
    db.close()


def test_app_settings_repository_upserts_and_decodes_values(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'settings.db'}")
    db.init_db()
    repo = Repository(db.session_maker())

    repo.save_app_settings({
        "risk_per_trade_pct": 0.75,
        "timeframes": ["1m", "5m", "1h"],
        "telegram_enabled": False,
    })
    repo.save_app_settings({"risk_per_trade_pct": 1.0})

    settings = repo.get_app_settings()
    assert settings == {
        "risk_per_trade_pct": 1.0,
        "timeframes": ["1m", "5m", "1h"],
        "telegram_enabled": False,
    }
    db.close()
