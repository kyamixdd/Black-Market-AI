"""Security and restart-recovery regression tests."""
from pathlib import Path

from core.disaster_recovery import PositionRecoveryManager
from database.connection import Database
from database.repositories import Repository
from paper_trading.simulator import Simulator
from core.event_bus import EventBus


def test_sqlite_connections_enable_durability_pragmas(tmp_path: Path):
    db = Database(f"sqlite:///{tmp_path / 'durable.db'}")
    db.init_db()
    with db.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 30000
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 2
    db.close()


def test_open_positions_survive_database_reopen_and_recover_once(tmp_path: Path):
    path = tmp_path / "restart.db"
    url = f"sqlite:///{path}"
    first = Database(url)
    first.init_db()
    repo = Repository(first.session_maker())
    repo.save_position({
        "position_id": "RESTART-SPOT-001", "symbol": "BTCUSDT", "market": "SPOT",
        "side": "LONG", "entry_price": 50000.0, "amount": 0.01,
        "current_price": 50500.0, "stop_loss": 49000.0, "take_profit": 52000.0,
        "leverage": 1.0, "unrealized_pnl": 5.0, "realized_pnl": 0.0,
        "fees_paid": 0.1, "status": "OPEN",
    })
    first.close()

    restarted = Database(url)
    restarted.init_db()
    simulator = Simulator(EventBus())
    recovery = PositionRecoveryManager(restarted, simulator)
    first_result = recovery.recover_positions()
    second_result = recovery.recover_positions()

    assert first_result["spot"] == 1
    assert second_result["spot"] == 1
    assert list(simulator.spot_positions) == ["RESTART-SPOT-001"]
    assert simulator.spot_positions["RESTART-SPOT-001"]["amount"] == 0.01
    restarted.close()
