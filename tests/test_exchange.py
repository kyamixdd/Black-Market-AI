"""Tests for exchange clients and market discovery."""

import pytest

pytestmark = pytest.mark.live  # These smoke tests call public Binance endpoints.

from exchange.futures_client import FuturesClient
from exchange.market_discovery import MarketDiscovery
from exchange.rate_limiter import RateLimiter
from exchange.spot_client import SpotClient
from exchange.symbol_registry import SymbolRegistry


@pytest.mark.asyncio
async def test_spot_client():
    limiter = RateLimiter()
    client = SpotClient(limiter)
    try:
        info = await client.get_exchange_info()
        assert "symbols" in info
        assert len(info["symbols"]) > 0
    finally:
        await client.close()

@pytest.mark.asyncio
async def test_futures_client():
    limiter = RateLimiter()
    client = FuturesClient(limiter)
    try:
        info = await client.get_exchange_info()
        assert "symbols" in info
        assert len(info["symbols"]) > 0
    finally:
        await client.close()

@pytest.mark.asyncio
async def test_market_discovery():
    limiter = RateLimiter()
    registry = SymbolRegistry()
    discovery = MarketDiscovery(registry, limiter)

    result = await discovery.discover_all()
    assert result["spot"] > 0
    assert result["futures"] > 0
    assert registry.count() > 0
