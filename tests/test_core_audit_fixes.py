"""Regression tests for the core audit repairs."""
import pytest

from core.event_bus import EventBus
from paper_trading.risk_manager import RiskManager
from paper_trading.simulator import Simulator


def test_daily_loss_limit_ignores_profitable_days():
    manager = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
    assert manager.check_daily_loss(25.0, 500.0) is True
    assert manager.check_daily_loss(-9.99, 500.0) is True
    assert manager.check_daily_loss(-10.0, 500.0) is False
    assert manager.check_daily_loss(-15.0, 500.0) is False


def test_position_size_rejects_invalid_balance_and_risk():
    manager = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
    assert manager.calculate_position_size(0.0, 1.0) == 0.0
    assert manager.calculate_position_size(100.0, 0.0) == 0.0


class CachedMarket:
    def get_volume(self, market, symbol):
        return 123456.0


def test_simulator_uses_real_cached_quote_volume():
    simulator = Simulator(EventBus(), CachedMarket())
    assert simulator._get_volume_24h("SPOT", "BTCUSDT") == 123456.0


def test_simulator_does_not_fake_volume_when_cache_is_missing():
    simulator = Simulator(EventBus())
    assert simulator._get_volume_24h("SPOT", "BTCUSDT") == 0.0


@pytest.mark.asyncio
async def test_spot_position_reserves_cash_and_returns_principal_on_close():
    simulator = Simulator(EventBus())
    # Deterministic fills and fees make the accounting assertion exact.
    simulator.fee_calc.get_fill_price = lambda market, side, order_type, price, *args: price
    simulator.fee_calc.calculate = lambda market, side, amount, price, leverage=1.0: (
        amount * price * 0.001 if market == "SPOT" else 0.0
    )
    signal = {
        "signal_id": "AUDIT-SPOT-CASH",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": [110.0],
        "leverage": 1.0,
    }

    position_id = await simulator.execute_signal(signal)
    assert position_id is not None
    position = simulator.spot_positions[position_id]
    reserved = position["reserved_notional"]
    assert reserved > 0
    assert simulator.spot_balance == pytest.approx(
        500.0 - reserved - position["fees_paid"]
    )
    assert reserved + position["fees_paid"] <= 500.0

    await simulator.update_prices("SPOT", "BTCUSDT", 100.0)
    assert position_id in simulator.spot_positions

    await simulator.update_prices("SPOT", "BTCUSDT", 110.0)
    assert position_id not in simulator.spot_positions
    assert simulator.spot_balance == pytest.approx(
        500.0 + simulator.closed_trades[-1]["pnl"]
    )


@pytest.mark.asyncio
async def test_spot_short_is_rejected():
    simulator = Simulator(EventBus())
    signal = {
        "signal_id": "AUDIT-SPOT-SHORT",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "SHORT",
        "entry": 100.0,
        "stop_loss": 101.0,
        "take_profit": [98.0],
        "leverage": 1.0,
    }
    assert await simulator.execute_signal(signal) is None
