"""Stage 6 paper-trading risk and execution integrity regressions."""
import asyncio
from datetime import datetime, timezone

import pytest

from core.event_bus import EventBus
from paper_trading.simulator import Simulator


def signal(symbol="COINUSDT", market="SPOT", direction="LONG", entry=100.0,
           stop=90.0, leverage=1.0, signal_id="S"):
    return {
        "signal_id": signal_id, "symbol": symbol, "market": market,
        "direction": direction, "entry": entry, "stop_loss": stop,
        "take_profit": [entry * 1.2], "leverage": leverage,
    }


@pytest.mark.asyncio
async def test_concurrent_openings_cannot_bypass_market_position_limit():
    sim = Simulator(EventBus())
    sim.risk_manager.max_spot_positions = 3
    requests = [sim.execute_signal(signal(f"ASSET{i}USDT", signal_id=f"CONCURRENT-{i}")) for i in range(12)]
    results = await asyncio.gather(*requests)
    assert sum(result is not None for result in results) == 3
    assert len(sim.spot_positions) == 3


@pytest.mark.asyncio
async def test_open_limit_order_reserves_position_slot_and_risk():
    sim = Simulator(EventBus())
    sim.risk_manager.max_spot_positions = 1
    order_id = await sim.place_limit_order(signal("ONEUSDT", entry=99, stop=90, signal_id="L1"))
    assert order_id is not None
    assert await sim.place_limit_order(signal("TWOUSDT", entry=99, stop=90, signal_id="L2")) is None
    assert len(sim.open_orders) == 1


@pytest.mark.asyncio
async def test_asset_exposure_is_shared_across_spot_and_futures():
    sim = Simulator(EventBus())
    sim.risk_manager.max_asset_exposure_pct = 3.0
    spot = signal("BTCUSDT", "SPOT", "LONG", 1000, 900, 1, "ASSET-SPOT")
    futures = signal("BTCUSDT", "FUTURES", "LONG", 1000, 900, 3, "ASSET-FUTURES")
    assert await sim.execute_signal(spot) is not None
    assert await sim.execute_signal(futures) is None
    assert len(sim.spot_positions) == 1
    assert len(sim.futures_positions) == 0


@pytest.mark.asyncio
async def test_position_notional_cap_rejects_oversized_manual_quantity():
    sim = Simulator(EventBus())
    request = signal("BTCUSDT", entry=1000, stop=999, signal_id="OVERSIZE")
    assert await sim.execute_signal(request, quantity_override=1.0) is None
    assert not sim.spot_positions


@pytest.mark.asyncio
async def test_invalid_leverage_is_rejected():
    sim = Simulator(EventBus())
    request = signal("BTCUSDT", "FUTURES", "LONG", 1000, 900, 0, "BAD-LEV")
    assert await sim.execute_signal(request) is None
    assert not sim.futures_positions


@pytest.mark.asyncio
async def test_auto_sizing_accounts_for_extreme_fill_gap():
    sim = Simulator(EventBus())
    sim.fee_calc.get_fill_price = lambda market, side, order_type, price, amount, *args: price * 1.5
    request = signal("GAPUSDT", entry=100, stop=90, signal_id="GAP")
    position_id = await sim.execute_signal(request)
    assert position_id is not None
    position = sim.spot_positions[position_id]
    equity = sim.get_account_equity_breakdown()["total_equity"]
    risk = abs(position["entry_price"] - position["stop_loss"]) * position["amount"]
    assert risk <= equity * sim.risk_manager.max_risk_pct / 100 + 1e-8


def test_risk_manager_rejects_nonfinite_or_negative_risk_inputs():
    from paper_trading.risk_manager import RiskManager

    manager = RiskManager(0.5, 2, 3, 3, 5, 5)
    assert not manager.check_total_risk(float("nan"), 1, 1000)
    assert not manager.check_total_risk(-1, 1, 1000)
    assert not manager.check_trade_risk(float("inf"), 1000)


@pytest.mark.asyncio
async def test_restart_restores_daily_loss_baseline_and_blocks_new_risk():
    sim = Simulator(EventBus())
    sim.daily_start_equity = 1000.0
    sim.daily_pnl_date = datetime.now(timezone.utc).date()
    sim.spot_balance -= 30.0
    state = sim.get_state_snapshot()

    restored = Simulator(EventBus())
    restored.restore_state(state)
    assert restored.get_daily_pnl() <= -30.0
    assert await restored.execute_signal(signal("RECOVERYUSDT", signal_id="RECOVER-RISK")) is None


@pytest.mark.asyncio
async def test_extreme_futures_gap_cannot_drive_simulated_account_below_zero():
    sim = Simulator(EventBus())
    request = signal("GAPFUTUSDT", "FUTURES", "LONG", 1000, 900, 3, "FUT-GAP")
    position_id = await sim.execute_signal(request)
    assert position_id is not None
    position = sim.futures_positions[position_id]
    reserved_margin = position["reserved_margin"]

    await sim.update_prices("FUTURES", "GAPFUTUSDT", 1.0, mark_price=1.0)
    assert not sim.futures_positions
    assert sim.futures_balance >= -1e-8
    assert sim.closed_trades[-1]["close_reason"] == "LIQUIDATION"
    assert sim.closed_trades[-1]["pnl"] >= -reserved_margin - position["fees_paid"] - 1e-6
