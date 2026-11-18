"""Offline tests for public exchange client routing and market discovery."""

import pytest

from exchange.futures_client import FuturesClient
from exchange.market_discovery import MarketDiscovery
from exchange.rate_limiter import RateLimiter
from exchange.spot_client import SpotClient
from exchange.symbol_registry import SymbolRegistry


@pytest.mark.asyncio
async def test_spot_client_uses_public_exchange_info_endpoint(monkeypatch):
    client = SpotClient(RateLimiter())
    calls = []

    async def fake_get(path, params=None, timeout=30.0):
        calls.append((path, params))
        return {"symbols": [{"symbol": "BTCUSDT"}]}

    monkeypatch.setattr(client, "_get", fake_get)
    info = await client.get_exchange_info()
    assert info["symbols"][0]["symbol"] == "BTCUSDT"
    assert calls == [("/api/v3/exchangeInfo", None)]
    await client.close()


@pytest.mark.asyncio
async def test_futures_client_uses_public_exchange_info_endpoint(monkeypatch):
    client = FuturesClient(RateLimiter())
    calls = []

    async def fake_get(path, params=None, timeout=30.0):
        calls.append((path, params))
        return {"symbols": [{"symbol": "BTCUSDT"}]}

    monkeypatch.setattr(client, "_get", fake_get)
    info = await client.get_exchange_info()
    assert info["symbols"][0]["symbol"] == "BTCUSDT"
    assert calls == [("/fapi/v1/exchangeInfo", None)]
    await client.close()


@pytest.mark.asyncio
async def test_market_discovery_registers_spot_and_futures_symbols(monkeypatch):
    registry = SymbolRegistry()
    discovery = MarketDiscovery(registry, RateLimiter())

    spot = {
        "symbols": [{
            "symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC",
            "quoteAsset": "USDT", "pricePrecision": 2, "quantityPrecision": 5,
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
            ],
        }]
    }
    futures = {
        "symbols": [{
            "symbol": "ETHUSDT", "status": "TRADING", "baseAsset": "ETH",
            "quoteAsset": "USDT", "pricePrecision": 2, "quantityPrecision": 3,
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        }]
    }

    async def fake_fetch(url):
        return futures if "fapi.binance.com" in url else spot

    monkeypatch.setattr(discovery, "_fetch", fake_fetch)
    result = await discovery.discover_all()
    assert result == {"spot": 1, "futures": 1}
    assert registry.is_eligible("BTCUSDT", "SPOT")
    assert registry.is_eligible("ETHUSDT", "FUTURES")



@pytest.mark.asyncio
async def test_live_kline_websocket_updates_candles_and_persists_closed_bar():
    from core.orchestrator import Orchestrator
    from market.candle_manager import CandleManager

    class FakeRepo:
        def __init__(self):
            self.saved = []

        def save_candles(self, candles):
            self.saved.extend(candles)

    class FakeEventBus:
        def __init__(self):
            self.events = []

        async def publish(self, event):
            self.events.append(event)

    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator._analysis_timeframes = ("1m", "5m")
    orchestrator._ws_connected = False
    orchestrator._last_ws_message_at = None
    orchestrator.candle_manager = CandleManager()
    orchestrator.repo = FakeRepo()
    orchestrator.event_bus = FakeEventBus()

    base = {
        "e": "kline",
        "s": "BTCUSDT",
        "k": {
            "i": "1m", "t": 1_800_000_000_000, "T": 1_800_000_059_999,
            "o": "100", "h": "105", "l": "99", "c": "103", "v": "12",
            "x": False,
        },
    }
    await orchestrator._on_exchange_ws_message({"_market": "SPOT", "data": base})
    current = orchestrator.candle_manager.get_series("SPOT", "BTCUSDT", "1m")
    assert len(current) == 1
    assert current[-1]["close"] == 103
    assert orchestrator.repo.saved == []

    closed = {**base, "k": {**base["k"], "x": True}}
    await orchestrator._on_exchange_ws_message({"_market": "SPOT", "data": closed})
    assert len(orchestrator.repo.saved) == 1
    assert orchestrator.repo.saved[0]["symbol"] == "BTCUSDT"
    assert orchestrator.repo.saved[0]["timeframe"] == "1m"
    assert orchestrator.event_bus.events[-1].payload["candle"]["closed"] is True
