"""Offline tests for the shared market-data reliability contract."""
import asyncio
import time
import pytest
from market.data_reliability import (
    MarketDataHealth, MarketDataState, TTLCache, valid_symbol, valid_price,
    valid_volume, validate_candle,
)
from market.candle_manager import CandleManager


def test_symbol_price_volume_validation():
    assert valid_symbol("BTCUSDT")
    assert not valid_symbol("btc/usdt")
    assert not valid_symbol("BTC USDT")
    assert valid_price("12.5") and not valid_price(float("nan"))
    assert valid_volume("0") and not valid_volume("-1")


def test_candle_validation_rejects_bad_values_and_future_time():
    now = 1_700_000_000_000
    assert validate_candle(now - 60_000, 10, 12, 9, 11, 100, now - 1, now_ms=now)
    assert not validate_candle(now - 60_000, 10, 8, 9, 11, 100, now - 1, now_ms=now)
    assert not validate_candle(now - 60_000, 10, 12, 9, 11, -1, now - 1, now_ms=now)
    assert not validate_candle(now + 60_000, 10, 12, 9, 11, 100, now + 60_001, now_ms=now)
    assert not validate_candle(now - 60_000, 10, 12, 9, 11, 100, now + 60_000, now_ms=now)


def test_candle_manager_deduplicates_rejects_invalid_and_detects_missing():
    manager = CandleManager()
    base = 1_700_000_000_000
    assert manager.add_candle("SPOT", "BTCUSDT", "1m", base, 10, 12, 9, 11, 5, base + 59_999)
    assert not manager.add_candle("SPOT", "BTCUSDT", "1m", base, 10, 12, 9, 11, 5, base + 59_999)
    assert not manager.add_candle("SPOT", "BTCUSDT", "1m", base + 60_000, 10, 8, 9, 11, 5, base + 119_999)
    assert manager.add_candle("SPOT", "BTCUSDT", "1m", base + 180_000, 11, 13, 10, 12, 6, base + 239_999)
    assert manager.detect_missing_candles("SPOT", "BTCUSDT", "1m") == [base + 60_000, base + 120_000]


def test_candle_cache_is_bounded_and_sorted_on_out_of_order_insert():
    manager = CandleManager()
    base = 1_700_000_000_000
    for offset in (120_000, 0, 60_000):
        assert manager.add_candle("SPOT", "ETHUSDT", "1m", base + offset, 10, 12, 9, 11, 1)
    series = manager.get_series("SPOT", "ETHUSDT", "1m")
    assert [row["open_time"] for row in series] == [base, base + 60_000, base + 120_000]
    manager._max_per_series = 2
    manager.add_candle("SPOT", "ETHUSDT", "1m", base + 180_000, 10, 12, 9, 11, 1)
    assert len(manager.get_series("SPOT", "ETHUSDT", "1m")) == 2


@pytest.mark.asyncio
async def test_historical_collection_rejects_empty_and_stale_exchange_responses():
    manager = CandleManager()

    class Client:
        def __init__(self, rows):
            self.rows = rows

        async def get_klines(self, *_args, **_kwargs):
            return self.rows

    assert await manager.collect_historical(
        Client([]), Client([]), "SPOT", "BTCUSDT", "1h",
    ) == 0
    empty_status = manager.get_collection_status("SPOT", "BTCUSDT", "1h")
    assert empty_status["state"] == "FAILED"
    assert empty_status["error"] == "empty_response"

    stale_open = int(time.time() * 1000) - 15 * 60 * 60 * 1000
    stale_row = [
        stale_open, "100", "102", "99", "101", "10",
        stale_open + 60 * 60 * 1000 - 1,
    ]
    assert await manager.collect_historical(
        Client([stale_row]), Client([]), "SPOT", "BTCUSDT", "1h",
    ) == 1
    stale_status = manager.get_collection_status("SPOT", "BTCUSDT", "1h")
    assert stale_status["state"] == "FAILED"
    assert stale_status["error"].startswith("stale_latest_candle:")
    assert stale_status["latest_candle_age_seconds"] > 14 * 60 * 60


@pytest.mark.asyncio
async def test_historical_collection_discards_unclosed_candles():
    manager = CandleManager()

    class Client:
        async def get_klines(self, *_args, **_kwargs):
            now = int(time.time() * 1000)
            open_time = now - now % 3_600_000
            return [[
                open_time, "100", "102", "99", "101", "10",
                open_time + 3_600_000 - 1,
            ]]

    client = Client()
    assert await manager.collect_historical(client, client, "SPOT", "BTCUSDT", "1h") == 0
    status = manager.get_collection_status("SPOT", "BTCUSDT", "1h")
    assert status["state"] == "FAILED"
    assert status["error"] == "no_valid_closed_candles"


@pytest.mark.asyncio
async def test_historical_collection_uses_exchange_clock_when_local_clock_is_behind():
    manager = CandleManager()
    offset_ms = 13 * 60 * 60 * 1000

    class Client:
        def now_ms(self):
            return int(time.time() * 1000) + offset_ms

        async def get_klines(self, *_args, **_kwargs):
            now_ms = self.now_ms()
            close_time = now_ms - 60_000
            open_time = close_time - 3_600_000 + 1
            return [[open_time, "100", "102", "99", "101", "10", close_time]]

    client = Client()
    assert await manager.collect_historical(
        client, client, "SPOT", "BTCUSDT", "1h",
    ) == 1
    status = manager.get_collection_status("SPOT", "BTCUSDT", "1h")
    assert status["state"] == "SUCCESS"
    assert manager.current_time_ms() >= client.now_ms() - 1_000


@pytest.mark.asyncio
async def test_exchange_clock_sync_initial_offset_and_failure_fallback(monkeypatch):
    from exchange.base_client import BasePublicClient
    from exchange.rate_limiter import RateLimiter
    import exchange.base_client as base_client_module

    local_now_ms = int(time.time() * 1000)
    offset_ms = 13 * 60 * 60 * 1000
    client = BasePublicClient(
        RateLimiter(), "https://example.invalid", "test",
        server_time_path="/time",
    )
    requests = 0

    async def successful_time_request(*_args, **_kwargs):
        nonlocal requests
        requests += 1
        return {"serverTime": local_now_ms + offset_ms}

    monkeypatch.setattr(client, "_get", successful_time_request)
    monkeypatch.setattr(base_client_module.time, "monotonic", lambda: 10.0)
    assert await client.sync_clock_if_due(interval_seconds=300)
    assert client.now_ms() == pytest.approx(local_now_ms + offset_ms, abs=1_000)
    assert not await client.sync_clock_if_due(interval_seconds=300)
    assert requests == 1

    async def failed_time_request(*_args, **_kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(client, "_get", failed_time_request)
    monkeypatch.setattr(base_client_module.time, "monotonic", lambda: 400.0)
    assert not await client.sync_clock_if_due(interval_seconds=300)
    assert client.now_ms() == pytest.approx(local_now_ms + offset_ms, abs=1_000)


def test_health_status_distinguishes_live_delayed_stale_and_reconnecting():
    health = MarketDataHealth(stale_after_ms=120_000, delayed_after_ms=30_000)
    health.mark_success("REST", exchange_event_ms=900, received_ms=1_000)
    assert health.snapshot(now_ms=1_010).state == MarketDataState.LIVE
    assert health.snapshot(now_ms=31_000).state == MarketDataState.DELAYED
    assert health.snapshot(now_ms=121_000).state == MarketDataState.STALE
    health.set_connection(MarketDataState.RECONNECTING, "stream dropped")
    assert health.snapshot(now_ms=1_000_000).state == MarketDataState.RECONNECTING


def test_ttl_cache_expires_and_enforces_capacity():
    cache = TTLCache(max_entries=2, ttl_seconds=5)
    cache.set("a", 1, now=10)
    cache.set("b", 2, now=10)
    assert cache.get("a", now=14) == 1
    cache.set("c", 3, now=14)
    assert len(cache) == 2
    assert cache.get("b", now=14) is None
    assert cache.get("a", now=16) is None

def test_market_cache_reports_source_and_freshness():
    from market.market_cache import MarketCache

    cache = MarketCache()
    unavailable = cache.get_data_status("SPOT")
    assert unavailable["state"] == "UNAVAILABLE"
    cache.update_ticker("SPOT", "BTCUSDT", 100, 10, 1, source="WEBSOCKET")
    status = cache.get_data_status("SPOT")
    assert status["state"] == "LIVE"
    assert status["data_source"] == "WEBSOCKET"
    assert status["latest_symbol"] == "BTCUSDT"

@pytest.mark.asyncio
async def test_websocket_manager_exposes_offline_and_reconnecting_state():
    from exchange.rate_limiter import RateLimiter
    from exchange.websocket_manager import WebSocketManager

    manager = WebSocketManager(RateLimiter())
    assert manager.status_snapshot()["state"] == "OFFLINE"
    manager._running = True
    manager._spot_streams = ["btcusdt@ticker"]
    manager._tasks = [asyncio.create_task(asyncio.sleep(10))]
    assert manager.status_snapshot()["state"] == "RECONNECTING"
    manager._tasks[0].cancel()
    await asyncio.gather(*manager._tasks, return_exceptions=True)
    manager._tasks.clear()
    manager._running = False


def test_websocket_status_requires_each_configured_market_to_be_live():
    from exchange.rate_limiter import RateLimiter
    from exchange.websocket_manager import WebSocketManager

    manager = WebSocketManager(RateLimiter())
    manager._running = True
    manager._spot_streams = ["btcusdt@ticker"]
    manager._futures_streams = ["btcusdt@ticker"]
    manager._connected_by_market["SPOT"] = 1
    manager._last_message_by_market["SPOT"] = int(time.time() * 1000)

    status = manager.status_snapshot()
    assert status["state"] == "PARTIAL"
    assert status["markets"]["SPOT"]["state"] == "LIVE"
    assert status["markets"]["FUTURES"]["state"] == "RECONNECTING"

    manager._connected_by_market["FUTURES"] = 1
    manager._last_message_by_market["FUTURES"] = int(time.time() * 1000)
    status = manager.status_snapshot()
    assert status["state"] == "LIVE"
    assert status["markets"]["FUTURES"]["state"] == "LIVE"
