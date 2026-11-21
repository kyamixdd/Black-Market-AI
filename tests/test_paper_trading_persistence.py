from datetime import datetime, timezone
import sqlite3

from sqlalchemy import inspect

from config import FUTURES_INITIAL_BALANCE, SPOT_INITIAL_BALANCE
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
        assert {"reserved_notional", "last_funding_time", "order_id", "signal_id", "strategy", "order_type"} <= position_columns
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


def test_limit_fill_event_failure_is_durable_and_reconciles_after_restart(tmp_path):
    class FailingPositionEventBus(EventBus):
        def __init__(self):
            super().__init__()
            self.fail_position_event = True

        async def publish(self, event):
            if event.event_type == "POSITION_OPENED" and self.fail_position_event:
                self.fail_position_event = False
                raise RuntimeError("simulated event dispatch failure")
            await super().publish(event)

    db = Database(f"sqlite:///{tmp_path / 'durable-fill.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())

        def persist_order(order):
            repo.save_order({
                "order_id": order["order_id"],
                "signal_id": order.get("signal_id"),
                "symbol": order["symbol"],
                "market": order["market"],
                "order_type": order["order_type"],
                "side": order["side"],
                "amount": order["amount"],
                "price": order.get("entry_price", order.get("price")),
                "stop_loss": order.get("stop_loss"),
                "take_profit": order.get("take_profit"),
                "status": order["status"],
                "filled_amount": order.get("filled_amount", 0.0),
                "avg_fill_price": order.get("avg_fill_price", 0.0),
                "fee": order.get("fee", 0.0),
                "leverage": order.get("leverage", 1.0),
                "created_at": order.get("created_at"),
            })

        simulator = Simulator(FailingPositionEventBus())
        simulator.persist_order_callback = persist_order
        simulator.persist_position_callback = repo.save_position
        simulator.persist_trade_callback = repo.save_trade_history
        signal = {
            "signal_id": "SIG-DURABLE-LIMIT",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "direction": "LONG",
            "entry": 49000.0,
            "stop_loss": 48000.0,
            "take_profit": [52000.0],
            "leverage": 1.0,
        }

        import asyncio

        async def run_fill():
            placed_id = await simulator.place_limit_order(signal)
            await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)
            return placed_id

        order_id = asyncio.run(run_fill())

        assert order_id not in simulator.open_orders
        assert len(simulator.spot_positions) == 1
        assert repo.get_open_orders() == []
        persisted_position = repo.get_open_positions("SPOT")[0]
        assert persisted_position.order_id == order_id

        recovered_simulator = Simulator(EventBus())
        PositionRecoveryManager(db, recovered_simulator).recover_positions()
        assert len(recovered_simulator.spot_positions) == 1
        assert recovered_simulator.spot_balance == simulator.spot_balance
        assert recovered_simulator.open_orders == {}
    finally:
        db.close()



def test_futures_funding_timestamp_and_fee_survive_restart_without_double_charge(tmp_path):
    import asyncio

    db = Database(f"sqlite:///{tmp_path / 'funding-recovery.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        position = {
            "position_id": "POS-FUNDING-1",
            "symbol": "BTCUSDT",
            "market": "FUTURES",
            "side": "LONG",
            "entry_price": 100.0,
            "amount": 1.0,
            "current_price": 100.0,
            "stop_loss": 90.0,
            "take_profit": 120.0,
            "leverage": 2.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "fees_paid": 0.0,
            "last_funding_time": 0,
            "reserved_notional": 0.0,
            "reserved_margin": 100.0,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc).replace(microsecond=0) - __import__("datetime").timedelta(hours=9),
        }
        repo.save_position(position)
        simulator = Simulator(EventBus())
        simulator.futures_positions[position["position_id"]] = position
        simulator.persist_position_callback = repo.save_position

        asyncio.run(simulator._apply_funding(position, 0.001))
        charged_balance = simulator.futures_balance
        charged_fee = position["fees_paid"]
        charged_timestamp = position["last_funding_time"]

        persisted = repo.get_open_positions("FUTURES")[0]
        assert persisted.last_funding_time == charged_timestamp
        assert persisted.fees_paid == charged_fee

        restored = Simulator(EventBus())
        PositionRecoveryManager(db, restored).recover_positions()
        restored_position = restored.futures_positions[position["position_id"]]
        restored.persist_position_callback = repo.save_position
        asyncio.run(restored._apply_funding(restored_position, 0.001))

        assert restored_position["last_funding_time"] == charged_timestamp
        assert restored_position["fees_paid"] == charged_fee
        assert restored.futures_balance == charged_balance - position["reserved_margin"]
    finally:
        db.close()


def test_funding_persistence_failure_rolls_back_fee_timestamp_and_balance():
    import asyncio
    import pytest

    simulator = Simulator(EventBus())
    position = {
        "position_id": "POS-FUNDING-FAIL",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "side": "LONG",
        "entry_price": 100.0,
        "amount": 1.0,
        "leverage": 2.0,
        "fees_paid": 0.0,
        "last_funding_time": 0,
    }
    simulator.persist_position_callback = lambda _position: (_ for _ in ()).throw(RuntimeError("database unavailable"))
    balance_before = simulator.futures_balance

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(simulator._apply_funding(position, 0.001))

    assert position["fees_paid"] == 0.0
    assert position["last_funding_time"] == 0
    assert simulator.futures_balance == balance_before



def test_new_futures_position_waits_for_scheduled_funding_boundary():
    import asyncio

    simulator = Simulator(EventBus())
    opened_at = datetime.now(timezone.utc)
    position = {
        "position_id": "POS-NEW-FUNDING",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "side": "LONG",
        "entry_price": 100.0,
        "amount": 1.0,
        "leverage": 1.0,
        "fees_paid": 0.0,
        "last_funding_time": 0,
        "opened_at": opened_at,
    }
    balance_before = simulator.futures_balance

    asyncio.run(simulator._apply_funding(position, 0.001))

    assert position["last_funding_time"] == 0
    assert position["fees_paid"] == 0.0
    assert simulator.futures_balance == balance_before



def test_recovery_reconciles_closed_spot_and_futures_net_pnl(tmp_path):
    from datetime import timedelta

    db = Database(f"sqlite:///{tmp_path / 'closed-ledger.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        closed_at = datetime.now(timezone.utc)
        for market, pnl in (("SPOT", 12.5), ("FUTURES", -7.25)):
            repo.save_trade_history({
                "position_id": f"POS-{market}-CLOSED",
                "symbol": "BTCUSDT",
                "market": market,
                "side": "BUY" if market == "SPOT" else "LONG",
                "entry_price": 100.0,
                "exit_price": 110.0,
                "amount": 1.0,
                "leverage": 5.0 if market == "FUTURES" else 1.0,
                "pnl": pnl,
                "pnl_pct": pnl,
                "fee": 1.0,
                "strategy": "MANUAL",
                "signal_id": "MANUAL",
                "opened_at": closed_at - timedelta(hours=1),
                "closed_at": closed_at,
                "close_reason": "MANUAL",
            })

        simulator = Simulator(EventBus())
        PositionRecoveryManager(db, simulator).recover_positions()

        assert simulator.spot_balance == SPOT_INITIAL_BALANCE + 12.5
        assert simulator.futures_balance == FUTURES_INITIAL_BALANCE - 7.25
        assert len(simulator.closed_trades) == 2
        assert simulator.daily_pnl == 5.25
    finally:
        db.close()


def test_recovery_deducts_open_position_costs_and_futures_funding_once(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'open-ledger.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        spot = _open_spot_position()
        futures = {
            "position_id": "POS-FUTURES-OPEN",
            "symbol": "ETHUSDT",
            "market": "FUTURES",
            "side": "LONG",
            "entry_price": 2000.0,
            "amount": 0.5,
            "current_price": 2010.0,
            "stop_loss": 1900.0,
            "take_profit": 2200.0,
            "leverage": 10.0,
            "unrealized_pnl": 5.0,
            "realized_pnl": 0.0,
            "fees_paid": 2.75,
            "last_funding_time": 1795200000000,
            "reserved_notional": 0.0,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
        }
        repo.save_position(spot)
        repo.save_position(futures)

        simulator = Simulator(EventBus())
        PositionRecoveryManager(db, simulator).recover_positions()

        assert simulator.spot_balance == SPOT_INITIAL_BALANCE - 201.0
        assert simulator.futures_balance == FUTURES_INITIAL_BALANCE - 100.0 - 2.75
        assert simulator.spot_positions[spot["position_id"]]["fees_paid"] == 1.0
        assert simulator.futures_positions[futures["position_id"]]["last_funding_time"] == 1795200000000
    finally:
        db.close()



def test_recovery_restores_futures_reserved_margin_once(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'futures-margin.db'}")
    db.init_db()
    try:
        repo = Repository(db.session_maker())
        position = {
            "position_id": "POS-MARGIN-RECOVERY",
            "symbol": "BTCUSDT",
            "market": "FUTURES",
            "side": "LONG",
            "entry_price": 1000.0,
            "amount": 2.0,
            "current_price": 1000.0,
            "stop_loss": 900.0,
            "take_profit": 1200.0,
            "leverage": 4.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "fees_paid": 1.0,
            "last_funding_time": 0,
            "reserved_notional": 0.0,
            "reserved_margin": 500.0,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
        }
        repo.save_position(position)
        simulator = Simulator(EventBus())
        PositionRecoveryManager(db, simulator).recover_positions()
        assert simulator.futures_balance == FUTURES_INITIAL_BALANCE - 501.0
        recovered = simulator.futures_positions["POS-MARGIN-RECOVERY"]
        assert recovered["reserved_margin"] == 500.0
    finally:
        db.close()
