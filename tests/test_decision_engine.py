"""Regression coverage for validated signal event construction."""
from unittest.mock import AsyncMock

import pytest

from core.event_models import EventType
from intelligence.decision_engine import DecisionEngine


@pytest.mark.asyncio
async def test_validated_signal_event_keeps_symbol_and_market_once():
    bus = AsyncMock()
    engine = DecisionEngine(bus)
    engine.validator.validate = lambda signal: (True, "")
    engine.confidence_engine.calculate = lambda signal: 0.9
    signal = {
        "signal_id": "signal-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "side": "LONG",
    }

    await engine.evaluate_signal(signal)

    event = bus.publish.await_args.args[0]
    assert event.event_type == EventType.SIGNAL_VALIDATED.value
    assert event.symbol == "BTCUSDT"
    assert event.market == "SPOT"
    assert event.payload["signal_id"] == "signal-1"
