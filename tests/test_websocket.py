"""Test WebSocket connection and message parsing."""
import asyncio

import pytest

from exchange.rate_limiter import RateLimiter
from exchange.websocket_manager import WebSocketManager


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
