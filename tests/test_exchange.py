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
        return spot if "api.binance.com" in url else futures

    monkeypatch.setattr(discovery, "_fetch", fake_fetch)
    result = await discovery.discover_all()
    assert result == {"spot": 1, "futures": 1}
    assert registry.is_eligible("BTCUSDT", "SPOT")
    assert registry.is_eligible("ETHUSDT", "FUTURES")
