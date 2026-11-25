"""Test strategies and paper trading simulator."""

import numpy as np
import pytest

from core.event_bus import EventBus
from paper_trading.simulator import Simulator
from strategies.momentum import MomentumStrategy


def test_momentum_strategy():
    strategy = MomentumStrategy()
    # Generate mock closes with strong upward momentum
    closes = np.linspace(100.0, 110.0, 50)
    highs = closes + 0.5
    lows = closes - 0.5
    volumes = np.full(50, 1000.0)

    ohlc_data = {
        "15m": {
            "close": closes,
            "high": highs,
            "low": lows,
            "volume": volumes,
        }
    }

    signal = strategy.analyze("BTCUSDT", "SPOT", ohlc_data)
    assert signal is not None
    assert signal["symbol"] == "BTCUSDT"
    assert signal["strategy"] == "momentum"
    assert signal["direction"] in ("LONG", "BUY")


@pytest.mark.asyncio
async def test_paper_trading_simulator():
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-TEST-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0, 55000.0],
        "leverage": 1.0,
    }

    pos_id = await sim.execute_signal(signal)
    assert pos_id is not None
    assert len(sim.spot_positions) == 1

    # Simulate price reaching target
    await sim.update_prices("SPOT", "BTCUSDT", 53000.0)
    assert len(sim.spot_positions) == 0
    assert len(sim.closed_trades) == 1
    assert sim.closed_trades[0]["pnl"] > 0
