"""Test WebSocket connection management and message parsing deterministically."""
import asyncio
import json
import logging

import pytest

from exchange.rate_limiter import RateLimiter
from exchange.websocket_manager import WebSocketManager


@pytest.mark.asyncio
async def test_websocket_manager(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    limiter = RateLimiter()
    manager = WebSocketManager(limiter)
    received_data = []
    received_both_markets = asyncio.Event()

    class FakeConnection:
        def __init__(self):
            self.sent = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

        async def recv(self):
            if not self.sent:
                self.sent = True
                return json.dumps({"e": "24hrTicker", "s": "BTCUSDT", "c": "50000"})
            await asyncio.Future()

    async def handler(data):
        received_data.append(data)
        if {item.get("_market") for item in received_data} == {"SPOT", "FUTURES"}:
            received_both_markets.set()

    manager.add_handler(handler)
    monkeypatch.setattr(
        "exchange.websocket_manager.websockets.connect",
        lambda *_args, **_kwargs: FakeConnection(),
    )

    await manager.start(["btcusdt@ticker"], ["btcusdt@ticker"])
    try:
        await asyncio.wait_for(received_both_markets.wait(), timeout=1)
    finally:
        await manager.stop()

    assert len(received_data) == 2
    assert {item["_market"] for item in received_data} == {"SPOT", "FUTURES"}
    assert "WebSocket connected for SPOT" in caplog.text
    assert "WebSocket connected for FUTURES" in caplog.text
