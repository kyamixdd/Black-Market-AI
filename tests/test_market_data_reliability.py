"""Offline tests for the shared market-data reliability contract."""
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

def test_websocket_manager_exposes_offline_and_reconnecting_state():
    from exchange.rate_limiter import RateLimiter
    from exchange.websocket_manager import WebSocketManager

    manager = WebSocketManager(RateLimiter())
    assert manager.status_snapshot()["state"] == "OFFLINE"
    manager._running = True
    manager._tasks = [__import__("asyncio").create_task(__import__("asyncio").sleep(10))]
    assert manager.status_snapshot()["state"] == "RECONNECTING"
    manager._tasks[0].cancel()
    manager._running = False
