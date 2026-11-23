"""Offline tests for Stage 6 event-driven monitoring."""
import asyncio
from datetime import datetime, timezone

import pytest

from core.event_models import Event, EventType, make_event
from src_tauri.backend.realtime_intelligence import RealtimeIntelligence


class Bus:
    def __init__(self):
        self.handlers = []
    def subscribe_all(self, handler):
        self.handlers.append(handler)


def event(event_id, symbol="BTCUSDT", market="SPOT", price=101):
    return Event(event_id=event_id, event_type=EventType.MARKET_DATA.value,
                 source="test", symbol=symbol, market=market,
                 payload={"price": price})


def test_monitoring_validation_and_owner_isolation():
    service = RealtimeIntelligence(Bus())
    task = service.create_task("owner-a", "btcusdt", "spot", "price_above", 100, ttl_seconds=60)
    assert task["symbol"] == "BTCUSDT"
    assert service.list_tasks("owner-b") == []
    assert service.cancel_task("owner-b", task["task_id"]) is False
    assert service.cancel_task("owner-a", task["task_id"]) is True
    assert service.list_tasks("owner-a")[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_event_triggers_matching_monitor_only_and_deduplicates():
    service = RealtimeIntelligence(Bus())
    task = service.create_task("u", "BTCUSDT", "SPOT", "price_above", 100, ttl_seconds=60)
    await service.process_event(event("e1", price=101))
    await service.process_event(event("e1", price=101))
    record = service.list_tasks("u")[0]
    assert record["task_id"] == task["task_id"]
    assert record["status"] == "triggered"
    assert record["trigger_count"] == 1
    assert service.status_snapshot()["duplicate_events"] == 1


@pytest.mark.asyncio
async def test_queue_backpressure_keeps_newest_event():
    service = RealtimeIntelligence(Bus(), queue_capacity=1)
    await service.on_event(event("old", price=99))
    await service.on_event(event("new", price=102))
    assert service.queue.qsize() == 1
    assert service.queue.get_nowait().event_id == "new"
    service.queue.task_done()
    assert service.status_snapshot()["dropped_events"] == 1


@pytest.mark.asyncio
async def test_event_worker_lifecycle_subscribes_and_stops():
    bus = Bus()
    service = RealtimeIntelligence(bus)
    await service.start()
    assert service.status_snapshot()["running"] is True
    assert service.on_event in bus.handlers
    await service.stop()
    assert service.status_snapshot()["running"] is False
    assert service.on_event not in bus.handlers
