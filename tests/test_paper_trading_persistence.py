from datetime import datetime, timezone
import sqlite3

from sqlalchemy import inspect

from config import SPOT_INITIAL_BALANCE
from core.disaster_recovery import PositionRecoveryManager
from core.event_bus import EventBus
from database.connection import Database
from database.repositories import Repository
from paper_trading.simulator import Simulator


def _open_limit_order(order_id: str, status: str = "FILLING") -> dict:
    return {
        "order_id": order_id,
        "signal_id": "MANUAL",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "order_type": "LIMIT",
        "side": "BUY",
        "amount": 2.0,
        "price": 100.0,
        "stop_loss": 90.0,
        "take_profit": 120.0,
        "status": status,
        "filled_amount": 0.0,
        "avg_fill_price": 0.0,
        "fee": 0.1,
        "leverage": 1.0,
        "created_at": datetime.now(timezone.utc),
    }


def _open_spot_position(order_id: str | None = None) -> dict:
    return {
        "position_id": "POS-RECOVERY-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "BUY",
        "entry_price": 100.0,
        "amount": 2.0,
        "current_price": 101.0,
        "stop_loss": 90.0,
        "take_profit": 120.0,
        "leverage": 1.0,
        "unrealized_pnl": 2.0,
        "realized_pnl": 0.0,
        "fees_paid": 1.0,
        "reserved_notional": 200.0,
        "order_id": order_id,
        "signal_id": "MANUAL",
        "strategy": "MANUAL",
        "order_type": "LIMIT",
        "status": "OPEN",
        "opened_at": datetime.now(timezone.utc),
    }


def test_database_init_migrates_existing_paper_trading_tables(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_positions (
                position_id VARCHAR(64) PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(16) NOT NULL,
                side VARCHAR(16) NOT NULL,
                entry_price FLOAT NOT NULL,
                amount FLOAT NOT NULL,
                current_price FLOAT NOT NULL,
                stop_loss FLOAT,
                take_profit FLOAT,
                leverage FLOAT,
                unrealized_pnl FLOAT,
                realized_pnl FLOAT,
                fees_paid FLOAT,
                status VARCHAR(16),
                opened_at DATETIME,
                closed_at DATETIME,
                close_price FLOAT
            );
            CREATE TABLE trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id VARCHAR(64) NOT NULL,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(16) NOT NULL,
                side VARCHAR(16) NOT NULL,
                entry_price FLOAT NOT NULL,
                exit_price FLOAT NOT NULL,
                amount FLOAT NOT NULL,
                leverage FLOAT,
                pnl FLOAT NOT NULL,
                pnl_pct FLOAT NOT NULL,
                fee FLOAT,
                strategy VARCHAR(32),
                signal_id VARCHAR(64),
                opened_at DATETIME NOT NULL,
                closed_at DATETIME,
                close_reason VARCHAR(32)
            );
            """
        )

    db = Database(f"sqlite:///{db_path}")
    db.init_db()
    try:
        inspector = inspect(db.engine)
        position_columns = {column["name"] for column in inspector.get_columns("paper_positions")}
        trade_columns = {column["name"] for column in inspector.get_columns("trade_history")}
        assert {"reserved_notional", "order_id", "signal_id", "strategy", "order_type"} <= position_columns
        assert "order_id" in trade_columns
    finally:
        db.close()


def test_repository_persists_full_simulator_position_shape(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'paper.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        position = _open_spot_position("ORD-SHAPE")
        repo.save_position(position)

        restored = repo.get_open_positions("SPOT")
        assert len(restored) == 1
        assert restored[0].order_id == "ORD-SHAPE"
        assert restored[0].reserved_notional == 200.0
        assert restored[0].strategy == "MANUAL"
        assert restored[0].order_type == "LIMIT"
    finally:
        db.close()


def test_recovery_reconciles_filling_order_and_restores_spot_reserved_balance(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'recovery.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        repo.save_position(_open_spot_position("ORD-MATCHED"))
        repo.save_order(_open_limit_order("ORD-MATCHED"))

        simulator = Simulator(EventBus())
        recovery = PositionRecoveryManager(db, simulator)
        result = recovery.recover_positions()

        assert result["spot"] == 1
        assert simulator.spot_balance == SPOT_INITIAL_BALANCE - 201.0
        assert "ORD-MATCHED" not in simulator.open_orders
        assert repo.get_open_orders() == []
    finally:
        db.close()


def test_recovery_holds_unmatched_filling_order_for_review(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'review.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        repo.save_order(_open_limit_order("ORD-AMBIGUOUS"))

        simulator = Simulator(EventBus())
        recovery = PositionRecoveryManager(db, simulator)
        recovery.recover_positions()

        assert simulator.open_orders["ORD-AMBIGUOUS"]["status"] == "RECOVERY_REVIEW"
        persisted = repo.get_open_orders()
        assert len(persisted) == 1
        assert persisted[0].status == "RECOVERY_REVIEW"
    finally:
        db.close()


def test_completed_trade_order_id_reconciles_filling_order_after_position_closed(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'closed-recovery.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        repo.save_order(_open_limit_order("ORD-CLOSED"))
        repo.save_trade_history({
            "position_id": "POS-CLOSED",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "side": "BUY",
            "entry_price": 100.0,
            "exit_price": 110.0,
            "amount": 2.0,
            "leverage": 1.0,
            "pnl": 18.0,
            "pnl_pct": 9.0,
            "fee": 2.0,
            "strategy": "MANUAL",
            "signal_id": "MANUAL",
            "order_id": "ORD-CLOSED",
            "opened_at": datetime.now(timezone.utc),
            "closed_at": datetime.now(timezone.utc),
            "close_reason": "MANUAL",
        })

        simulator = Simulator(EventBus())
        recovery = PositionRecoveryManager(db, simulator)
        recovery.recover_positions()

        assert "ORD-CLOSED" not in simulator.open_orders
        assert repo.get_open_orders() == []
        assert len(simulator.closed_trades) == 1
        assert simulator.closed_trades[0]["order_id"] == "ORD-CLOSED"
    finally:
        db.close()
