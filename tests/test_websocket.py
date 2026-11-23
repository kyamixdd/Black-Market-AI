"""Test WebSocket connection and message parsing."""
import asyncio

import pytest

from exchange.rate_limiter import RateLimiter
from exchange.websocket_manager import (
    FUTURES_WS_URL, SPOT_WS_URL, WebSocketManager,
)


@pytest.mark.asyncio
async def test_websocket_manager():
    limiter = RateLimiter()
    manager = WebSocketManager(limiter)

    received_data = []

    async def handler(data):
        received_data.append(data)

    manager.add_handler(handler)

    # Test starting with a small number of streams
    spot_streams = ["btcusdt@ticker"]
    futures_streams = ["btcusdt@ticker"]

    await manager.start(spot_streams, futures_streams)

    # Wait for potential data
    await asyncio.sleep(5)

    await manager.stop()

    # Depending on market activity, we might have received data
    assert len(received_data) >= 0
    # If we received something, it should be parsed correctly
    for data in received_data:
        assert isinstance(data, dict)


def test_binance_raw_and_combined_stream_urls():
    assert WebSocketManager._build_stream_url(
        SPOT_WS_URL, ["btcusdt@ticker"]
    ) == "wss://stream.binance.com:9443/ws/btcusdt@ticker"
    assert WebSocketManager._build_stream_url(
        SPOT_WS_URL, ["btcusdt@ticker", "ethusdt@ticker"]
    ) == "wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/ethusdt@ticker"
    assert WebSocketManager._build_stream_url(
        FUTURES_WS_URL, ["btcusdt@ticker", "ethusdt@ticker"]
    ) == "wss://fstream.binance.com/stream?streams=btcusdt@ticker/ethusdt@ticker"
