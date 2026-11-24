"""Test event bus functionality."""
import asyncio

import pytest

from core.event_bus import EventBus
from core.event_models import EventType, make_event


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe():
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(EventType.MARKET_DATA, handler)

    event = make_event(EventType.MARKET_DATA, "test", symbol="BTCUSDT", price=50000.0)
    await bus.publish(event)

    # Run the bus to process events
    bus_task = asyncio.create_task(bus.run())

    # Wait for processing
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].event_type == EventType.MARKET_DATA
    assert received[0].payload["price"] == 50000.0

    await bus.stop()
    bus_task.cancel()
