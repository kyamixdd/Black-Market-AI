"""Test Phase 5 paper trading features: slippage, spread, limit orders, funding, liquidation, risk management."""

from datetime import datetime, timedelta, timezone

import asyncio

import pytest

from core.event_bus import EventBus
from paper_trading.fee_calculator import FeeCalculator
from paper_trading.funding_calculator import FundingCalculator
from paper_trading.liquidation_engine import LiquidationEngine
from paper_trading.risk_manager import RiskManager
from paper_trading.simulator import Simulator


class TestFeeCalculator:
    """Test fee, slippage, and spread calculations."""

    def test_spot_fee_calculation(self):
        calc = FeeCalculator()
        fee = calc.calculate("SPOT", "BUY", 0.1, 50000.0, 1.0)
        expected = 0.1 * 50000.0 * 0.001  # 0.1%
        assert fee == expected

    def test_futures_fee_calculation(self):
        calc = FeeCalculator()
        fee = calc.calculate("FUTURES", "LONG", 0.1, 50000.0, 3.0)
        expected = 0.1 * 50000.0 * 3.0 * 0.0005  # 0.05%
        assert fee == expected

    def test_slippage_market_order_spot(self):
        calc = FeeCalculator()
        slip = calc.calculate_slippage("SPOT", "MARKET", 0.1, 50000.0, 1.0, 1000000.0)
        # Base slippage 5 bps = 0.05%
        assert slip > 0

    def test_slippage_limit_order(self):
        calc = FeeCalculator()
        slip = calc.calculate_slippage("SPOT", "LIMIT", 0.1, 50000.0)
        assert slip == 0.0

    def test_fill_price_buy(self):
        calc = FeeCalculator()
        fill = calc.get_fill_price("SPOT", "BUY", "MARKET", 50000.0, 0.1, 1.0, 1000000.0)
        assert fill > 50000.0  # Buy fills higher

    def test_fill_price_sell(self):
        calc = FeeCalculator()
        fill = calc.get_fill_price("SPOT", "SELL", "MARKET", 50000.0, 0.1, 1.0, 1000000.0)
        assert fill < 50000.0  # Sell fills lower

    def test_spread_calculation(self):
        calc = FeeCalculator()
        spread = calc.calculate_spread("SPOT", 50000.0)
        expected = 50000.0 * 2 / 10000  # 2 bps
        assert spread == expected


class TestRiskManager:
    """Test risk management functions."""

    def test_daily_loss_check(self):
        rm = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
        # Daily loss 1% of balance - should pass
        assert rm.check_daily_loss(-5.0, 500.0) is True
        # Daily loss 3% of balance - should fail (exceeds 2%)
        assert rm.check_daily_loss(-15.0, 500.0) is False

    def test_position_limit_check(self):
        rm = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
        positions = {"p1": {"status": "OPEN"}, "p2": {"status": "OPEN"}}
        assert rm.check_position_limit(positions, 5) is True
        assert rm.check_position_limit(positions, 2) is False

    def test_symbol_exposure_check(self):
        rm = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
        positions = {"p1": {"symbol": "BTCUSDT", "status": "OPEN"}}
        assert rm.check_symbol_exposure(positions, "BTCUSDT") is False
        assert rm.check_symbol_exposure(positions, "ETHUSDT") is True

    def test_total_risk_check(self):
        rm = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
        # Current risk $10, new risk $5, balance $500 -> 3% = limit
        assert rm.check_total_risk(10.0, 5.0, 500.0) is True
        # New risk $6 -> 3.2% > 3% limit
        assert rm.check_total_risk(10.0, 6.0, 500.0) is False

    def test_position_size_calculation(self):
        rm = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
        # Balance $500, risk per trade 0.5% = $2.5 risk budget, risk amount $100 -> 0.025 units
        size = rm.calculate_position_size(500.0, 100.0)
        assert size == 0.025

    def test_leverage_validation(self):
        rm = RiskManager(0.5, 2.0, 3.0, 3.0, 5, 5)
        assert rm.validate_leverage("SPOT", 5.0) == 5.0  # No cap on spot
        assert rm.validate_leverage("FUTURES", 5.0) == 3.0  # Capped at 3x


class TestLiquidationEngine:
    """Test futures liquidation logic."""

    def test_long_liquidation_price(self):
        le = LiquidationEngine()
        pos = {"market": "FUTURES", "side": "LONG", "entry_price": 50000.0, "leverage": 3.0}
        liq_price = le.calculate_liquidation_price(pos)
        # 50000 * (1 - 1/3 + 0.05) = 50000 * 0.7167 = 35833.33
        assert abs(liq_price - 35833.33) < 1.0

    def test_short_liquidation_price(self):
        le = LiquidationEngine()
        pos = {"market": "FUTURES", "side": "SHORT", "entry_price": 50000.0, "leverage": 3.0}
        liq_price = le.calculate_liquidation_price(pos)
        # 50000 * (1 + 1/3 - 0.05) = 50000 * 1.2833 = 64166.67
        assert abs(liq_price - 64166.67) < 1.0

    def test_long_liquidation_check(self):
        le = LiquidationEngine()
        pos = {"market": "FUTURES", "side": "LONG", "entry_price": 50000.0, "leverage": 3.0}
        assert le.check_liquidation(pos, 35000.0) is True  # Below liq price
        assert le.check_liquidation(pos, 40000.0) is False  # Above liq price

    def test_short_liquidation_check(self):
        le = LiquidationEngine()
        pos = {"market": "FUTURES", "side": "SHORT", "entry_price": 50000.0, "leverage": 3.0}
        assert le.check_liquidation(pos, 65000.0) is True  # Above liq price
        assert le.check_liquidation(pos, 60000.0) is False  # Below liq price

    def test_spot_not_liquidated(self):
        le = LiquidationEngine()
        pos = {"market": "SPOT", "side": "LONG", "entry_price": 50000.0}
        assert le.check_liquidation(pos, 10000.0) is False

    def test_margin_ratio(self):
        le = LiquidationEngine()
        pos = {"market": "FUTURES", "side": "LONG", "entry_price": 50000.0, "leverage": 3.0}
        # At entry price, margin ratio = 3.0
        assert abs(le.get_margin_ratio(pos, 50000.0) - 3.0) < 0.01
        # At 45000, pnl = -10%, margin ratio = 0.9 * 3 = 2.7
        assert abs(le.get_margin_ratio(pos, 45000.0) - 2.7) < 0.01

    def test_margin_risk_detection(self):
        le = LiquidationEngine()
        pos = {"market": "FUTURES", "side": "LONG", "entry_price": 50000.0, "leverage": 3.0}
        # At 38000, margin ratio ~ 2.28, threshold * MMR = 1.2 * 0.05 = 0.06
        # 2.28 > 0.06, so not at risk
        assert le.is_at_risk(pos, 38000.0) is False
        # At 36000, margin ratio ~ 2.16, still above 0.06
        assert le.is_at_risk(pos, 36000.0) is False


class TestFundingCalculator:
    """Test funding payment calculations."""

    def test_long_funding_payment(self):
        fc = FundingCalculator()
        pos = {"market": "FUTURES", "side": "LONG", "amount": 0.1, "entry_price": 50000.0, "leverage": 3.0}
        payment = fc.calculate(pos, 0.0001)  # 0.01%
        expected = 0.1 * 50000.0 * 3.0 * 0.0001
        assert payment == expected

    def test_short_funding_payment(self):
        fc = FundingCalculator()
        pos = {"market": "FUTURES", "side": "SHORT", "amount": 0.1, "entry_price": 50000.0, "leverage": 3.0}
        payment = fc.calculate(pos, 0.0001)
        expected = 0.1 * 50000.0 * 3.0 * 0.0001
        # Shorts receive when rate is positive (negative payment = they receive)
        assert payment == -expected

    def test_spot_no_funding(self):
        fc = FundingCalculator()
        pos = {"market": "SPOT", "side": "LONG", "amount": 0.1, "entry_price": 50000.0}
        payment = fc.calculate(pos, 0.0001)
        assert payment == 0.0

    def test_funding_intervals(self):
        fc = FundingCalculator()
        times = fc.get_funding_times(0, 24 * 3600 * 1000 - 1)  # Just before 24h
        # Should have 3 funding times in 24 hours (0, 8h, 16h)
        assert len(times) == 3


@pytest.mark.asyncio
async def test_paper_trading_slippage():
    """Test that slippage is applied to fills."""
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-SLIP-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }

    pos_id = await sim.execute_signal(signal)
    assert pos_id is not None
    position = sim.spot_positions[pos_id]
    # Fill price should be worse than signal entry due to spread+slippage
    assert position["entry_price"] > 50000.0


@pytest.mark.asyncio
async def test_paper_trading_limit_order():
    """Test limit order placement and filling."""
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-LIMIT-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 49000.0,  # Below current price
        "stop_loss": 48000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }

    # Place limit order
    order_id = await sim.place_limit_order(signal)
    assert order_id is not None
    assert order_id in sim.open_orders

    # Price moves down to limit price - should fill
    await sim.check_limit_orders("SPOT", "BTCUSDT", 49000.0)
    assert order_id not in sim.open_orders
    assert len(sim.spot_positions) == 1


@pytest.mark.asyncio
async def test_paper_trading_funding():
    """Test funding payments are applied."""
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-FUND-001",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 3.0,
    }

    pos_id = await sim.execute_signal(signal)
    position = sim.futures_positions[pos_id]
    initial_balance = sim.futures_balance

    # Apply funding
    await sim._apply_funding(position, 0.0001)  # 0.01%

    # Balance should decrease (longs pay when rate positive)
    assert sim.futures_balance < initial_balance


@pytest.mark.asyncio
async def test_paper_trading_liquidation():
    """Test futures liquidation."""
    bus = EventBus()
    sim = Simulator(bus)

    # Set stop_loss below liquidation price so liquidation triggers first
    # Liquidation price for 3x LONG at 50000 = 50000 * (1 - 1/3 + 0.05) = 35833
    signal = {
        "signal_id": "SIG-LIQ-001",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 35000.0,  # Below liquidation price
        "take_profit": [52000.0],
        "leverage": 3.0,
    }

    await sim.execute_signal(signal)
    assert len(sim.futures_positions) == 1

    # Price drops to liquidation level (~35833 for 3x long)
    await sim.update_prices("FUTURES", "BTCUSDT", 35000.0, mark_price=35000.0)
    assert len(sim.futures_positions) == 0
    assert len(sim.closed_trades) == 1
    assert sim.closed_trades[0]["close_reason"] == "LIQUIDATION"


@pytest.mark.asyncio
async def test_risk_daily_loss_protection():
    """Test daily loss limit prevents new positions."""
    bus = EventBus()
    sim = Simulator(bus)

    # Manually set daily PnL to exceed limit (2% of $1000 = $20)
    sim.daily_pnl = -25.0

    signal = {
        "signal_id": "SIG-RISK-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }

    pos_id = await sim.execute_signal(signal)
    assert pos_id is None  # Should be rejected


@pytest.mark.asyncio
async def test_risk_max_positions():
    """Test max positions limit."""
    bus = EventBus()
    sim = Simulator(bus)

    # Fill up to max (5 for spot)
    for i in range(5):
        signal = {
            "signal_id": f"SIG-MAX-{i}",
            "symbol": f"COIN{i}USDT",
            "market": "SPOT",
            "direction": "LONG",
            "entry": 100.0 + i,
            "stop_loss": 90.0 + i,
            "take_profit": [120.0 + i],
            "leverage": 1.0,
        }
        await sim.execute_signal(signal)

    assert len(sim.spot_positions) == 5

    # 6th should fail
    signal = {
        "signal_id": "SIG-MAX-6",
        "symbol": "COIN6USDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 106.0,
        "stop_loss": 96.0,
        "take_profit": [126.0],
        "leverage": 1.0,
    }
    pos_id = await sim.execute_signal(signal)
    assert pos_id is None


@pytest.mark.asyncio
async def test_risk_symbol_exposure():
    """Test one position per symbol limit."""
    bus = EventBus()
    sim = Simulator(bus)

    signal1 = {
        "signal_id": "SIG-EXP-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    await sim.execute_signal(signal1)
    assert len(sim.spot_positions) == 1

    # Second signal same symbol
    signal2 = {
        "signal_id": "SIG-EXP-2",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 51000.0,
        "stop_loss": 50000.0,
        "take_profit": [53000.0],
        "leverage": 1.0,
    }
    pos_id = await sim.execute_signal(signal2)
    assert pos_id is None


@pytest.mark.asyncio
async def test_paper_trading_state_snapshot():
    """Test state snapshot and restore for restart recovery."""
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-STATE-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    await sim.execute_signal(signal)

    # Get snapshot
    state = sim.get_state_snapshot()
    assert state["spot_balance"] < 500.0
    assert len(state["spot_positions"]) == 1
    assert len(state["closed_trades"]) == 0

    # Create new simulator and restore
    bus2 = EventBus()
    sim2 = Simulator(bus2)
    sim2.restore_state(state)

    assert sim2.spot_balance == state["spot_balance"]
    assert len(sim2.spot_positions) == 1


def test_daily_pnl_rolls_over_at_utc_day_boundary():
    simulator = Simulator(EventBus())
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    simulator.daily_pnl = -12.0
    simulator.daily_pnl_date = yesterday

    assert simulator.get_daily_pnl() == 0.0

    simulator.restore_state({"daily_pnl": -8.0, "daily_pnl_date": yesterday.isoformat()})
    assert simulator.get_daily_pnl() == 0.0


@pytest.mark.asyncio
async def test_paper_trading_short_pnl():
    """Test short position P&L calculation."""
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-SHORT-001",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "direction": "SHORT",
        "entry": 50000.0,
        "stop_loss": 51000.0,
        "take_profit": [48000.0],
        "leverage": 3.0,
    }

    await sim.execute_signal(signal)

    # Price drops - short should profit
    await sim.update_prices("FUTURES", "BTCUSDT", 48000.0)
    assert len(sim.futures_positions) == 0
    assert len(sim.closed_trades) == 1
    assert sim.closed_trades[0]["pnl"] > 0


@pytest.mark.asyncio
async def test_paper_trading_stop_loss():
    """Test stop loss execution."""
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-SL-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }

    await sim.execute_signal(signal)

    # Price hits stop loss
    await sim.update_prices("SPOT", "BTCUSDT", 48900.0)
    assert len(sim.spot_positions) == 0
    assert len(sim.closed_trades) == 1
    assert sim.closed_trades[0]["close_reason"] == "STOP_LOSS"
    assert sim.closed_trades[0]["pnl"] < 0


@pytest.mark.asyncio
async def test_paper_trading_take_profit():
    """Test take profit execution."""
    bus = EventBus()
    sim = Simulator(bus)

    signal = {
        "signal_id": "SIG-TP-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }

    await sim.execute_signal(signal)

    # Price hits take profit
    await sim.update_prices("SPOT", "BTCUSDT", 52100.0)
    assert len(sim.spot_positions) == 0
    assert len(sim.closed_trades) == 1
    assert sim.closed_trades[0]["close_reason"] == "TAKE_PROFIT"
    assert sim.closed_trades[0]["pnl"] > 0


@pytest.mark.asyncio
async def test_realized_trade_pnl_includes_entry_and_exit_fees():
    sim = Simulator(EventBus())
    sim.fee_calc.calculate = lambda *args: 0.1
    sim.fee_calc.get_fill_price = lambda market, side, order_type, price, *args: price
    signal = {
        "signal_id": "SIG-FEE-001",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }

    await sim.execute_signal(signal)
    await sim.update_prices("SPOT", "BTCUSDT", 52000.0)

    trade = sim.closed_trades[0]
    assert trade["fee"] == 0.2
    assert sim.spot_balance == pytest.approx(500.0 + trade["pnl"])
    assert sim.daily_pnl == pytest.approx(trade["pnl"])

@pytest.mark.asyncio
async def test_limit_order_remains_open_when_execution_is_temporarily_rejected():
    simulator = Simulator(EventBus())
    signal = {
        "signal_id": "SIG-LIMIT-RETRY",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 49000.0,
        "stop_loss": 48000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }

    order_id = await simulator.place_limit_order(signal)
    assert order_id is not None
    order = simulator.open_orders[order_id]

    # Simulate a balance/risk change after order placement but before the fill.
    simulator.spot_balance = 0.0
    await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)

    assert simulator.open_orders[order_id] is order
    assert order["status"] == "OPEN"
    assert simulator.spot_positions == {}

    # Once the account can support the order again, the same order can fill.
    simulator.spot_balance = simulator.initial_spot_balance
    await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)

    assert order_id not in simulator.open_orders
    assert order["status"] == "FILLED"
    assert len(simulator.spot_positions) == 1


@pytest.mark.asyncio
async def test_limit_order_execution_exception_does_not_lose_pending_order():
    simulator = Simulator(EventBus())
    signal = {
        "signal_id": "SIG-LIMIT-EXCEPTION",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 49000.0,
        "stop_loss": 48000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    order_id = await simulator.place_limit_order(signal)
    assert order_id is not None
    original_execute = simulator.execute_signal

    async def fail_execution(*_args, **_kwargs):
        raise RuntimeError("simulated execution failure")

    simulator.execute_signal = fail_execution
    await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)
    assert simulator.open_orders[order_id]["status"] == "OPEN"

    simulator.execute_signal = original_execute
    await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)
    assert order_id not in simulator.open_orders
    assert len(simulator.spot_positions) == 1


@pytest.mark.asyncio
async def test_cancel_limit_order_is_idempotent_and_publishes_cancellation():
    bus = EventBus()
    simulator = Simulator(bus)
    signal = {
        "signal_id": "SIG-LIMIT-CANCEL",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 49000.0,
        "stop_loss": 48000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    order_id = await simulator.place_limit_order(signal)
    assert order_id is not None

    cancelled = await simulator.cancel_limit_order(order_id)
    assert cancelled is not None
    assert cancelled["status"] == "CANCELLED"
    assert order_id not in simulator.open_orders
    assert await simulator.cancel_limit_order(order_id) is None

    placed_event = bus._queue.get_nowait()
    cancelled_event = bus._queue.get_nowait()
    assert placed_event.event_type == "ORDER_PLACED"
    assert cancelled_event.event_type == "TRADE_CANCELLED"
    assert cancelled_event.payload["order"]["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_concurrent_price_updates_cannot_double_fill_one_limit_order():
    simulator = Simulator(EventBus())
    signal = {
        "signal_id": "SIG-LIMIT-CONCURRENT",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 49000.0,
        "stop_loss": 48000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    order_id = await simulator.place_limit_order(signal)
    assert order_id is not None

    started = asyncio.Event()
    release = asyncio.Event()
    original_execute = simulator.execute_signal
    executions = 0

    async def delayed_execute(*args, **kwargs):
        nonlocal executions
        executions += 1
        started.set()
        await release.wait()
        return await original_execute(*args, **kwargs)

    simulator.execute_signal = delayed_execute
    first = asyncio.create_task(simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0))
    await started.wait()

    assert simulator.open_orders[order_id]["status"] == "FILLING"
    await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)
    assert executions == 1

    release.set()
    await first
    assert executions == 1
    assert order_id not in simulator.open_orders
    assert len(simulator.spot_positions) == 1


@pytest.mark.asyncio
async def test_position_close_is_idempotent_and_does_not_double_credit_balance():
    simulator = Simulator(EventBus())
    simulator.fee_calc.calculate = lambda *args: 0.0
    simulator.fee_calc.get_fill_price = lambda market, side, order_type, price, *args: price
    signal = {
        "signal_id": "SIG-CLOSE-ONCE",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    position_id = await simulator.execute_signal(signal)
    position = simulator.spot_positions[position_id]
    balance_before_close = simulator.spot_balance

    assert await simulator._close_position(position, 51000.0, "MANUAL") is True
    balance_after_close = simulator.spot_balance
    assert balance_after_close > balance_before_close
    assert await simulator._close_position(position, 51000.0, "MANUAL") is False
    assert simulator.spot_balance == pytest.approx(balance_after_close)
    assert len(simulator.closed_trades) == 1


@pytest.mark.asyncio
async def test_concurrent_position_close_attempts_only_realize_once():
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingEventBus(EventBus):
        async def publish(self, event):
            if event.event_type == "POSITION_CLOSED":
                started.set()
                await release.wait()
            await super().publish(event)

    simulator = Simulator(BlockingEventBus())
    simulator.fee_calc.calculate = lambda *args: 0.0
    simulator.fee_calc.get_fill_price = lambda market, side, order_type, price, *args: price
    signal = {
        "signal_id": "SIG-CLOSE-RACE",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    position_id = await simulator.execute_signal(signal)
    position = simulator.spot_positions[position_id]

    first = asyncio.create_task(simulator._close_position(position, 51000.0, "MANUAL"))
    await started.wait()
    assert position["status"] == "CLOSED"
    second = await simulator._close_position(position, 52000.0, "TAKE_PROFIT")
    assert second is False
    assert len(simulator.closed_trades) == 1

    release.set()
    assert await first is True
    assert len(simulator.closed_trades) == 1


def test_restore_marks_ambiguous_inflight_order_for_manual_reconciliation():
    simulator = Simulator(EventBus())
    state = simulator.get_state_snapshot()
    state["open_orders"] = {
        "ORD-IN-FLIGHT": {
            "order_id": "ORD-IN-FLIGHT",
            "status": "FILLING",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "side": "BUY",
            "entry_price": 50000.0,
            "amount": 0.001,
        }
    }

    restored = Simulator(EventBus())
    restored.restore_state(state)

    assert restored.open_orders["ORD-IN-FLIGHT"]["status"] == "RECOVERY_REVIEW"


@pytest.mark.asyncio
async def test_close_rejects_non_finite_fee_without_mutating_account():
    simulator = Simulator(EventBus())
    simulator.fee_calc.get_fill_price = lambda market, side, order_type, price, *args: price
    signal = {
        "signal_id": "SIG-CLOSE-BAD-FEE",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    position_id = await simulator.execute_signal(signal)
    position = simulator.spot_positions[position_id]
    balance_before = simulator.spot_balance
    simulator.fee_calc.calculate = lambda *args: float("nan")

    with pytest.raises(ValueError, match="non-finite"):
        await simulator._close_position(position, 51000.0, "MANUAL")

    assert position["status"] == "OPEN"
    assert position_id in simulator.spot_positions
    assert simulator.spot_balance == pytest.approx(balance_before)
    assert simulator.closed_trades == []


@pytest.mark.asyncio
async def test_liquidation_does_not_emit_false_alert_after_concurrent_manual_close():
    margin_alert_started = asyncio.Event()
    release_margin_alert = asyncio.Event()

    class PausingEventBus(EventBus):
        def __init__(self):
            super().__init__()
            self.published = []

        async def publish(self, event):
            self.published.append(event)
            payload = event.payload.get("payload", {})
            if event.event_type == "RISK_ALERT" and payload.get("alert_type") == "MARGIN_RISK":
                margin_alert_started.set()
                await release_margin_alert.wait()
            await super().publish(event)

    bus = PausingEventBus()
    simulator = Simulator(bus)
    signal = {
        "signal_id": "SIG-LIQ-CLOSE-RACE",
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "direction": "LONG",
        "entry": 50000.0,
        "stop_loss": 35000.0,
        "take_profit": [52000.0],
        "leverage": 3.0,
    }
    position_id = await simulator.execute_signal(signal)
    position = simulator.futures_positions[position_id]
    simulator.liquidation.is_at_risk = lambda *_args: True
    simulator.liquidation.check_liquidation = lambda *_args: True
    simulator.liquidation.calculate_liquidation_price = lambda *_args: 36000.0

    liquidation_task = asyncio.create_task(simulator._check_liquidation(position, 36000.0))
    await margin_alert_started.wait()

    assert await simulator._close_position(position, 40000.0, "MANUAL") is True
    release_margin_alert.set()
    await liquidation_task

    liquidation_alerts = [
        event for event in bus.published
        if event.event_type == "RISK_ALERT"
        and event.payload.get("payload", {}).get("alert_type") == "LIQUIDATION"
    ]
    assert liquidation_alerts == []
    assert len(simulator.closed_trades) == 1


@pytest.mark.asyncio
async def test_limit_order_is_not_retried_if_position_commits_before_event_failure():
    class FailingPositionEventBus(EventBus):
        def __init__(self):
            super().__init__()
            self.fail_position_event = True

        async def publish(self, event):
            if event.event_type == "POSITION_OPENED" and self.fail_position_event:
                self.fail_position_event = False
                raise RuntimeError("simulated event persistence failure")
            await super().publish(event)

    simulator = Simulator(FailingPositionEventBus())
    signal = {
        "signal_id": "SIG-LIMIT-COMMIT-THEN-FAIL",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "direction": "LONG",
        "entry": 49000.0,
        "stop_loss": 48000.0,
        "take_profit": [52000.0],
        "leverage": 1.0,
    }
    order_id = await simulator.place_limit_order(signal)
    assert order_id is not None

    await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)

    assert order_id not in simulator.open_orders
    assert len(simulator.spot_positions) == 1
    position = next(iter(simulator.spot_positions.values()))
    assert position["order_id"] == order_id
    await simulator.check_limit_orders("SPOT", "BTCUSDT", 49000.0)
    assert len(simulator.spot_positions) == 1


def test_restore_marks_order_filled_when_matching_position_was_persisted():
    simulator = Simulator(EventBus())
    state = simulator.get_state_snapshot()
    state["open_orders"] = {
        "ORD-PERSISTED-FILL": {
            "order_id": "ORD-PERSISTED-FILL",
            "status": "FILLING",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "side": "BUY",
            "entry_price": 50000.0,
            "amount": 0.001,
        }
    }
    state["spot_positions"] = {
        "POS-RECOVERED": {"position_id": "POS-RECOVERED", "order_id": "ORD-PERSISTED-FILL", "status": "OPEN"}
    }

    restored = Simulator(EventBus())
    restored.restore_state(state)

    assert "ORD-PERSISTED-FILL" not in restored.open_orders
