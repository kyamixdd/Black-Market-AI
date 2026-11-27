"""Test health monitor and scheduler."""
import asyncio

import pytest
from sqlalchemy import create_engine

from core.health_monitor import HealthMonitor
from core.observability import JsonLogFormatter, instrument_sql_engine
from core.scheduler import Scheduler


def test_health_monitor():
    hm = HealthMonitor()
    assert hm.get_status()["status"] == "UNKNOWN"
    assert hm.get_status()["metrics"]["uptime_seconds"] >= 0

    hm.check_component("DB", False, "Connection failed")
    assert hm.get_status()["status"] == "DEGRADED"
    assert hm.get_status()["components"]["DB"]["healthy"] is False

    hm.check_component("DB", True)
    assert hm.get_status()["status"] == "OK"
    assert hm.get_status()["components"]["DB"]["last_check"]


def test_sql_write_diagnostics_report_mutations_without_bound_values(caplog):
    import logging

    engine = create_engine("sqlite://")
    observer = instrument_sql_engine(engine)
    caplog.set_level(logging.INFO, logger="database.write")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE diagnostics_test (id INTEGER PRIMARY KEY, value TEXT)")
        connection.exec_driver_sql("INSERT INTO diagnostics_test (id, value) VALUES (?, ?)", (1, "private-value"))
    with pytest.raises(Exception):
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO diagnostics_test (id, value) VALUES (?, ?)", (1, "private-value"))

    observer.flush(force=True)
    messages = [JsonLogFormatter().format(record) for record in caplog.records]
    assert any('"event":"database_write_batch_summary"' in message and "INSERT diagnostics_test" in message for message in messages)
    assert any('"event":"database_write_failed"' in message for message in messages)
    assert all("private-value" not in message for message in messages)
    engine.dispose()


def test_orchestrator_health_snapshot_exposes_runtime_readiness():
    from types import SimpleNamespace

    from core.orchestrator import Orchestrator

    scanner_status = {
        "running": True,
        "configured_timeframes": ["1m", "1h"],
        "markets": {
            "SPOT": {"state": "COMPLETE", "refresh_failures": 0, "last_error": None},
            "FUTURES": {"state": "COMPLETE", "refresh_failures": 0, "last_error": None},
        },
    }
    runtime = SimpleNamespace(
        health_monitor=HealthMonitor(),
        db=object(),
        scanner=SimpleNamespace(
            enabled_markets={"SPOT", "FUTURES"},
            status_snapshot=lambda: scanner_status,
        ),
        ws_manager=SimpleNamespace(status_snapshot=lambda: {"state": "LIVE"}),
        intelligence=SimpleNamespace(predictor=SimpleNamespace(is_trained=False)),
        learning_service=SimpleNamespace(
            state="validation_failed",
            last_training_result={"reason": "holdout_threshold_not_met"},
            last_cycle_status="validation_failed",
        ),
        simulator=object(),
        registry=SimpleNamespace(count=lambda market: 10),
        _autonomous_enabled=True,
    )

    health = Orchestrator.refresh_health_status(runtime)

    assert health["status"] == "DEGRADED"
    assert health["components"]["market_scanner"]["healthy"] is True
    assert health["components"]["exchange_websocket"]["healthy"] is True
    assert health["components"]["learning_model"]["healthy"] is False
    assert "holdout_threshold_not_met" in health["components"]["learning_model"]["details"]
    assert health["metrics"]["eligible_symbols"] == {"SPOT": 10, "FUTURES": 10}


@pytest.mark.asyncio
async def test_scheduler():
    sc = Scheduler()
    count = 0

    async def task():
        nonlocal count
        count += 1

    sc.schedule(0.1, task)
    await sc.start()

    await asyncio.sleep(0.25)
    await sc.stop()

    assert count >= 2


@pytest.mark.asyncio
async def test_orchestrator_telegram_notifications_do_not_block_event_bus(tmp_path):
    import asyncio
    import time
    from core.event_models import EventType, make_event
    from core.orchestrator import Orchestrator
    from database.connection import Database

    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    db.init_db()
    orch = Orchestrator(db)

    sent = []

    class SlowTelegram:
        async def send_signal_update(self, signal, status):
            await asyncio.sleep(0.25)
            sent.append((signal.get("symbol"), status))

    orch.telegram = SlowTelegram()
    start = time.perf_counter()
    await orch._on_signal_rejected(
        make_event(EventType.SIGNAL_REJECTED, "test", symbol="BTCUSDT", market="SPOT", reason="low_conf")
    )
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1
    await asyncio.sleep(0.35)
    assert sent == [("BTCUSDT", "rejected")]
    await orch.stop()
    db.close()
