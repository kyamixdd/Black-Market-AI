"""Deterministic unit tests for Strategy Lab execution assumptions."""
from datetime import datetime, timezone

from learning.strategy_lab import LabConfig, STRATEGIES, run_strategy_lab


class FixtureStrategy:
    def analyze(self, symbol, market, data):
        close = float(data[next(iter(data))]["close"][-1])
        return {
            "direction": "LONG", "entry": close, "stop_loss": close - 2,
            "take_profit": [close + 2], "raw_score": 80,
        }


def candles(count=100):
    start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = []
    for i in range(count):
        close = 100.0 + i * 0.1
        rows.append({
            "open_time": start + i * 3600000,
            "close_time": start + (i + 1) * 3600000 - 1,
            "open": close, "high": close + 3, "low": close - 0.5,
            "close": close, "volume": 100.0,
        })
    return rows


def config(rows, **kwargs):
    return LabConfig(
        symbol="BTCUSDT", market="SPOT", timeframe="1h",
        start_time=rows[0]["open_time"], end_time=rows[-1]["close_time"],
        initial_capital=1000, risk_per_trade_pct=1,
        fee_rate=0.001, spread_bps=0, slippage_bps=0, **kwargs,
    )


def test_lab_uses_next_bar_open_for_entry_and_records_costs(monkeypatch):
    monkeypatch.setitem(STRATEGIES, "fixture", FixtureStrategy)
    rows = candles()
    result = run_strategy_lab(rows, config(rows), "fixture")
    assert result["status"] == "ok"
    closed = [trade for trade in result["trades"] if trade["status"] == "CLOSED"]
    assert closed
    first = closed[0]
    assert first["entry_time"] > first["signal_time"]
    assert first["entry_price"] == rows[51]["open"]
    assert first["fees"] > 0
    assert first["close_reason"] in {"STOP_LOSS", "TAKE_PROFIT", "END_OF_TEST"}


def test_lab_rejects_insufficient_history():
    rows = candles(40)
    result = run_strategy_lab(rows, config(rows), "momentum")
    assert result["status"] == "insufficient_data"
    assert result["trades"] == []


def test_lab_deduplicates_candle_timestamps_and_returns_metrics(monkeypatch):
    monkeypatch.setitem(STRATEGIES, "fixture", FixtureStrategy)
    rows = candles()
    rows = rows + [dict(rows[-1])]
    result = run_strategy_lab(rows, config(rows), "fixture")
    assert result["candle_count"] == 100
    assert result["metrics"]["trade_count"] == len([t for t in result["trades"] if t["status"] == "CLOSED"])
    assert result["metrics"]["max_drawdown_pct"] >= 0
    assert result["metrics"]["benchmark_buy_hold_return_pct"] is not None
