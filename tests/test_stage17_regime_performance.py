"""Tests for Stage 17 regime-conditioned Strategy Lab metrics."""
import pytest

from learning.regime_performance import performance_by_regime


def test_closed_trades_are_grouped_by_last_known_entry_regime():
    trades = [
        {"status": "CLOSED", "entry_time": 150, "exit_time": 3_600_150,
         "net_pnl": 20, "quantity": 1, "entry_fill": 100, "entry_price": 100},
        {"status": "CLOSED", "entry_time": 250, "exit_time": 7_200_250,
         "net_pnl": -10, "quantity": 2, "entry_fill": 100, "entry_price": 100},
        {"status": "OPEN", "entry_time": 300, "net_pnl": 1000},
    ]
    regimes = [
        {"timestamp": 100, "regime": "UPTREND"},
        {"timestamp": 200, "regime": "RANGE_BOUND"},
    ]
    result = performance_by_regime(trades, regimes, minimum_sample=2)
    assert result["regimes"]["UPTREND"]["trade_count"] == 1
    assert result["regimes"]["UPTREND"]["sample_status"] == "INSUFFICIENT_SAMPLE"
    assert result["regimes"]["RANGE_BOUND"]["net_pnl"] == -10
    assert result["unclassified_trades"] == 0


def test_trade_without_prior_regime_is_unclassified_and_insufficient():
    trades = [{"status": "CLOSED", "entry_time": 50, "exit_time": 60,
                "net_pnl": 2, "quantity": 1, "entry_price": 10}]
    result = performance_by_regime(trades, [], minimum_sample=1)
    assert result["unclassified_trades"] == 1
    assert result["status"] == "INSUFFICIENT_DATA"


def test_metrics_are_net_and_profit_factor_is_undefined_without_losses():
    trades = [{"status": "CLOSED", "entry_time": 100, "exit_time": 3_600_100,
                "net_pnl": 5, "quantity": 1, "entry_price": 50, "entry_fill": 50}]
    result = performance_by_regime(trades, [{"timestamp": 0, "regime": "UPTREND"}])
    metrics = result["regimes"]["UPTREND"]
    assert metrics["net_return_pct"] == pytest.approx(10)
    assert metrics["win_rate_pct"] == 100
    assert metrics["profit_factor"] is None
    assert metrics["average_holding_hours"] == pytest.approx(1)
