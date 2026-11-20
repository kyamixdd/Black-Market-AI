"""Focused tests for Phase 2 reliability and data-correctness remediation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from core.disaster_recovery import GracefulShutdownManager, PositionRecoveryManager, WebSocketReconnectionManager
from core.event_bus import EventBus
from core.event_models import EventType, make_event
from core.orchestrator import Orchestrator
from database.connection import Database
from database.repositories import Repository
from exchange.rate_limiter import RateLimiter
from exchange.websocket_manager import WebSocketManager
from paper_trading.simulator import Simulator


@pytest.fixture
def temporary_database(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'recovery.db'}")
    database.init_db()
    yield database
    database.close()


def test_position_recovery_restores_balances_daily_pnl_reserved_principal_and_open_fees(temporary_database):
    repo = Repository(temporary_database.session_maker())
    now = datetime.now(timezone.utc)
    repo.save_position({
        "position_id": "POS-OPEN-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "LONG",
        "entry_price": 100.0,
        "amount": 1.0,
        "current_price": 101.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "leverage": 1.0,
        "unrealized_pnl": 1.0,
        "realized_pnl": 0.0,
        "fees_paid": 2.0,
        "status": "OPEN",
        "opened_at": now,
    })
    repo.save_trade_history({
        "position_id": "POS-CLOSED-1",
        "symbol": "ETHUSDT",
        "market": "SPOT",
        "side": "LONG",
        "entry_price": 100.0,
        "exit_price": 105.0,
        "amount": 1.0,
        "pnl": 3.0,
        "pnl_pct": 3.0,
        "opened_at": now,
        "closed_at": now,
    })
    repo.save_trade_history({
        "position_id": "POS-CLOSED-2",
        "symbol": "SOLUSDT",
        "market": "FUTURES",
        "side": "SHORT",
        "entry_price": 100.0,
        "exit_price": 104.0,
        "amount": 1.0,
        "pnl": -4.0,
        "pnl_pct": -4.0,
        "opened_at": now,
        "closed_at": now,
    })
    repo.save_order({
        "order_id": "ORD-OPEN-1",
        "signal_id": "SIG-ORDER-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "order_type": "LIMIT",
        "side": "LONG",
        "amount": 0.1,
        "price": 99.0,
        "status": "OPEN",
        "created_at": now,
    })
    repo.save_signal({
        "signal_id": "SIG-ORDER-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "strategy": "MOMENTUM",
        "direction": "LONG",
        "timeframe": "15m",
        "entry": 99.0,
        "stop_loss": 95.0,
        "take_profit": [105.0],
        "raw_score": 0.8,
        "reasons": ["test"],
    })

    simulator = Simulator(EventBus())
    initial_spot = simulator.initial_spot_balance
    initial_futures = simulator.initial_futures_balance
    recovery = PositionRecoveryManager(temporary_database, simulator)

    assert recovery.recover_positions()["orders"] == 1

    assert simulator.spot_balance == initial_spot - 99.0
    assert simulator.futures_balance == initial_futures - 4.0
    assert simulator.get_daily_pnl() == -1.0
    assert len(simulator.spot_positions) == 1
    assert list(simulator.open_orders) == ["ORD-OPEN-1"]
    assert simulator.open_orders["ORD-OPEN-1"]["strategy"] == "MOMENTUM"

    recovery.recover_positions()
    assert simulator.spot_balance == initial_spot + 1.0
    assert len(simulator.spot_positions) == 1
    assert len(simulator.open_orders) == 1


def test_closed_position_is_not_recovered_as_open(temporary_database):
    repo = Repository(temporary_database.session_maker())
    opened_at = datetime.now(timezone.utc)
    repo.save_position({
        "position_id": "POS-CLOSED-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "LONG",
        "entry_price": 100.0,
        "amount": 1.0,
        "current_price": 101.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "leverage": 1.0,
        "unrealized_pnl": 1.0,
        "realized_pnl": 0.0,
        "fees_paid": 1.0,
        "status": "OPEN",
        "opened_at": opened_at,
    })

    repo.save_trade_history({
        "position_id": "POS-CLOSED-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "LONG",
        "entry_price": 100.0,
        "exit_price": 105.0,
        "amount": 1.0,
        "pnl_pct": 4.0,
        "pnl": 4.0,
        "fee": 2.0,
        "opened_at": opened_at,
        "closed_at": datetime.now(timezone.utc),
    })
    assert repo.get_open_positions("SPOT") == []


@pytest.mark.asyncio
async def test_open_position_is_persisted_when_open_event_is_handled(temporary_database):
    orchestrator = Orchestrator(temporary_database)
    position = {
        "position_id": "POS-OPEN-EVENT",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "LONG",
        "entry_price": 100.0,
        "amount": 1.0,
        "current_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "leverage": 1.0,
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "fees_paid": 1.0,
        "status": "OPEN",
        "opened_at": datetime.now(timezone.utc),
    }

    await orchestrator._on_position_opened(make_event(EventType.POSITION_OPENED, "test", position=position))

    assert [item.position_id for item in orchestrator.repo.get_open_positions("SPOT")] == ["POS-OPEN-EVENT"]


@pytest.mark.asyncio
async def test_order_events_persist_placement_and_filled_status(temporary_database):
    orchestrator = Orchestrator(temporary_database)
    order = {
        "order_id": "ORD-TEST-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "LONG",
        "entry_price": 99.0,
        "amount": 0.1,
        "stop_loss": 95.0,
        "take_profit": 105.0,
        "leverage": 1.0,
        "order_type": "LIMIT",
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc),
        "signal_id": "SIG-TEST-1",
    }

    await orchestrator._on_order_placed(make_event(EventType.ORDER_PLACED, "test", order=order))

    saved_open_orders = orchestrator.repo.get_open_orders("SPOT")
    assert [item.order_id for item in saved_open_orders] == ["ORD-TEST-1"]
    assert saved_open_orders[0].price == 99.0

    order["status"] = "FILLED"
    await orchestrator._on_order_filled(make_event(EventType.ORDER_FILLED, "test", order=order))

    assert orchestrator.repo.get_open_orders("SPOT") == []


@pytest.mark.asyncio
async def test_shutdown_awaits_awaitable_returned_by_sync_handler():
    completed = []
    shutdown = GracefulShutdownManager()

    async def finish():
        await asyncio.sleep(0)
        completed.append(True)

    shutdown.register_handler(lambda: finish())
    await shutdown.shutdown("test")

    assert completed == [True]


@pytest.mark.asyncio
async def test_event_bus_drains_pending_events_during_shutdown():
    event_bus = EventBus()
    processed = []

    async def record_event(event):
        processed.append(event.event_id)

    event_bus.subscribe("TEST_EVENT", record_event)
    event_task = asyncio.create_task(event_bus.run())
    await asyncio.sleep(0)
    for _ in range(3):
        await event_bus.publish(make_event("TEST_EVENT", "test"))

    await event_bus.stop()
    await event_task

    assert len(processed) == 3


@pytest.mark.asyncio
async def test_reconnection_restarts_existing_streams_without_duplicates():
    manager = WebSocketManager(RateLimiter())
    manager._run_stream = AsyncMock()
    await manager.start(["btcusdt@ticker"], [])
    await asyncio.sleep(0)

    reconnection = WebSocketReconnectionManager(
        manager,
        base_delay=0.001,
        max_delay=0.001,
        jitter=0,
        reconnect_callback=manager.restart,
    )
    await reconnection.start()

    assert await reconnection.handle_disconnect() is True
    await asyncio.sleep(0)
    assert manager._run_stream.await_count == 2
    assert len(manager._tasks) == 1

    await reconnection.stop()
    await manager.stop()


@pytest.mark.asyncio
async def test_production_orchestrator_starts_and_stops_disaster_recovery(temporary_database):
    orchestrator = Orchestrator(temporary_database)
    orchestrator._discovery.discover_all = AsyncMock(return_value={"spot": 0, "futures": 0})
    orchestrator.disaster_recovery.backup_manager.create_backup = Mock()
    orchestrator.spot_client.close = AsyncMock()
    orchestrator.futures_client.close = AsyncMock()

    await orchestrator.initialize()
    recovery_task = orchestrator.disaster_recovery.watchdog._monitor_task
    assert orchestrator.disaster_recovery._running is True
    assert recovery_task is not None

    await orchestrator.disaster_recovery.start()
    assert orchestrator.disaster_recovery.watchdog._monitor_task is recovery_task

    await orchestrator.stop()

    assert orchestrator.disaster_recovery._running is False
    assert orchestrator.disaster_recovery.watchdog._monitor_task is None
    orchestrator.disaster_recovery.backup_manager.create_backup.assert_called_once_with("shutdown")
