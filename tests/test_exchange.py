"""Offline tests for public exchange client routing and market discovery."""

import pytest

from exchange.futures_client import FuturesClient
from exchange.market_discovery import MarketDiscovery
from exchange.rate_limiter import RateLimiter
from exchange.spot_client import SpotClient
from exchange.websocket_manager import WebSocketManager
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


@pytest.mark.asyncio
async def test_combined_binance_stream_uses_correct_stream_endpoint(monkeypatch):
    from unittest.mock import AsyncMock
    import exchange.websocket_manager as websocket_module

    manager = WebSocketManager(RateLimiter())
    manager.rate_limiter.acquire = AsyncMock()
    received = []
    manager.add_handler(lambda message: _capture_message(received, message))
    manager._running = True
    urls = []

    class FakeSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def recv(self):
            manager._running = False
            return '{"data":{"e":"24hrTicker","s":"BTCUSDT"}}'

    def fake_connect(url, **_kwargs):
        urls.append(url)
        return FakeSocket()

    async def capture(message):
        received.append(message)

    async def _capture_message(target, message):
        target.append(message)

    monkeypatch.setattr(websocket_module.websockets, "connect", fake_connect)
    await manager._run_stream(
        websocket_module.SPOT_WS_URL,
        ["btcusdt@ticker", "btcusdt@kline_1m"],
        "SPOT",
    )

    assert urls == [
        "wss://data-stream.binance.vision/stream?streams=btcusdt@ticker/btcusdt@kline_1m"
    ]
    assert received[0]["_market"] == "SPOT"


@pytest.mark.asyncio
async def test_exchange_websocket_subscribes_bounded_ticker_and_configured_kline_streams(monkeypatch):
    import core.orchestrator as orchestrator_module
    from core.orchestrator import Orchestrator

    class FakeCache:
        def get_market_tickers(self, market):
            return [
                {"symbol": f"COIN{index}USDT", "volume_24h": 1000 - index}
                for index in range(100)
            ]

    class FakeWebSocketManager:
        def __init__(self):
            self.spot = None
            self.futures = None

        async def start(self, spot_streams, futures_streams):
            self.spot = spot_streams
            self.futures = futures_streams

    monkeypatch.setattr(orchestrator_module, "SPOT_ENABLED", True)
    monkeypatch.setattr(orchestrator_module, "USDM_FUTURES_ENABLED", False)
    monkeypatch.setattr(orchestrator_module, "MAX_WEBSOCKET_CONNECTIONS", 2)
    monkeypatch.setattr(orchestrator_module, "MAX_STREAMS_PER_CONNECTION", 100)

    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.cache = FakeCache()
    orchestrator._analysis_timeframes = ("1m", "5m", "1h")
    orchestrator.ws_manager = FakeWebSocketManager()

    await orchestrator._start_market_websockets()

    assert orchestrator.ws_manager.futures == []
    assert len(orchestrator.ws_manager.spot) <= 200
    assert "coin0usdt@ticker" in orchestrator.ws_manager.spot
    assert "coin0usdt@kline_1m" in orchestrator.ws_manager.spot
    assert "coin0usdt@kline_5m" in orchestrator.ws_manager.spot
    assert "coin0usdt@kline_1h" in orchestrator.ws_manager.spot
