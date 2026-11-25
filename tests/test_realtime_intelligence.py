"""Offline tests for Stage 6 event-driven monitoring."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.event_models import Event, EventType, make_event
from src_tauri.backend.realtime_intelligence import RealtimeIntelligence


class Bus:
    def __init__(self):
        self.handlers = []
    def subscribe_all(self, handler):
        self.handlers.append(handler)
    def unsubscribe_all(self, handler):
        while handler in self.handlers:
            self.handlers.remove(handler)


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


@pytest.mark.asyncio
async def test_scanner_publishes_validated_live_ticker_event():
    from market.scanner import Scanner

    class Registry:
        def is_eligible(self, symbol, market):
            return symbol == "BTCUSDT" and market == "SPOT"

    class Cache:
        def __init__(self):
            self.updated = []
        def update_ticker(self, *args, **kwargs):
            self.updated.append((args, kwargs))

    class CapturingBus:
        def __init__(self):
            self.events = []
        async def publish(self, event):
            self.events.append(event)

    scanner = Scanner.__new__(Scanner)
    scanner.registry = Registry()
    scanner.cache = Cache()
    scanner.event_bus = CapturingBus()
    now_ms = int(__import__("time").time() * 1000)
    scanner.spot_client = SimpleNamespace(now_ms=lambda: now_ms)
    await scanner._handle_stream_message("SPOT", {
        "data": {"s": "BTCUSDT", "c": "123.4", "q": "5000",
                 "P": "1.2", "E": now_ms}
    })
    assert len(scanner.cache.updated) == 1
    assert len(scanner.event_bus.events) == 1
    published = scanner.event_bus.events[0]
    assert published.event_type == EventType.MARKET_DATA
    assert published.symbol == "BTCUSDT"
    assert published.payload["price"] == 123.4
    assert published.payload["data_source"] == "WEBSOCKET"


@pytest.mark.asyncio
async def test_scanner_uses_futures_book_ticker_midpoint_with_rest_ticker_fields():
    from market.scanner import Scanner

    class Registry:
        def is_eligible(self, symbol, market):
            return symbol == "BTCUSDT" and market == "FUTURES"

    class Cache:
        def __init__(self):
            self.updated = []

        def get_volume(self, market, symbol):
            return 5000.0

        def get_change(self, market, symbol):
            return 1.2

        def update_book_ticker(self, *args, **kwargs):
            self.updated.append((args, kwargs))

    class CapturingBus:
        def __init__(self):
            self.events = []

        async def publish(self, event):
            self.events.append(event)

    scanner = Scanner.__new__(Scanner)
    scanner.registry = Registry()
    scanner.cache = Cache()
    scanner.event_bus = CapturingBus()
    scanner.futures_client = SimpleNamespace(
        now_ms=lambda: int(__import__("time").time() * 1000)
    )
    now_ms = scanner.futures_client.now_ms()

    await scanner._handle_stream_message("FUTURES", {
        "data": {
            "e": "bookTicker", "s": "BTCUSDT", "b": "123.3", "a": "123.5",
            "E": now_ms,
        }
    })

    assert scanner.cache.updated == [(("FUTURES", "BTCUSDT", 123.4), {})]
    assert scanner.event_bus.events[0].payload["price"] == 123.4
    assert scanner.event_bus.events[0].payload["volume_24h"] == 5000.0
    assert scanner.event_bus.events[0].payload["data_source"] == "WEBSOCKET_BOOK"

    await scanner._handle_stream_message("FUTURES", {
        "data": {
            "e": "bookTicker", "s": "BTCUSDT", "b": "123.6", "a": "123.5",
            "E": now_ms,
        }
    })
    assert len(scanner.cache.updated) == 1
    assert len(scanner.event_bus.events) == 1


@pytest.mark.asyncio
async def test_scanner_subscribes_to_futures_book_ticker_streams():
    from market.scanner import Scanner

    class Registry:
        def is_eligible(self, symbol, market):
            return symbol == "BTCUSDT" and market == "FUTURES"

    class Cache:
        def get_market_tickers(self, market):
            assert market == "FUTURES"
            return [{"symbol": "BTCUSDT", "volume_24h": 5000.0}]

    class WebSocketManager:
        def __init__(self):
            self.started = None

        async def start(self, spot_streams, futures_streams):
            self.started = (spot_streams, futures_streams)

    scanner = Scanner.__new__(Scanner)
    scanner.registry = Registry()
    scanner.cache = Cache()
    scanner.websocket_manager = WebSocketManager()
    scanner.stream_symbol_limit = 1
    scanner._stream_symbols = {"SPOT": (), "FUTURES": ()}

    await scanner._refresh_stream_subscriptions("FUTURES")

    assert scanner.websocket_manager.started == ([], ["btcusdt@bookTicker"])
