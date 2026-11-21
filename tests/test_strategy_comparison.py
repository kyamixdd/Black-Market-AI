"""Tests for comparable and leakage-aware strategy evaluation."""
import numpy as np

from learning.strategy_comparison import STRATEGY_NAMES, compare_strategies


def make_candles(n=420):
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0002, 0.008, n)
    close = 100 * np.cumprod(1 + returns)
    return [
        {
            "open_time": i * 3600000,
            "open": float(close[i - 1] if i else close[i]),
            "high": float(close[i] * 1.01),
            "low": float(close[i] * 0.99),
            "close": float(close[i]),
            "volume": float(rng.uniform(100, 1000)),
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "timeframe": "1h",
        }
        for i in range(n)
    ]


def test_strategy_comparison_returns_all_five_methods_on_same_oos_window():
    result = compare_strategies(make_candles())
    assert result["status"] == "ok"
    assert [item["strategy"] for item in result["strategies"]] == list(STRATEGY_NAMES)
    assert result["walk_forward_folds"] >= 1
    assert int(result["evaluation_start_time"]) < int(result["evaluation_end_time"])
    assert all(item["status"] == "evaluated" for item in result["strategies"])
    assert all(item["evaluation_bars"] == result["strategies"][0]["evaluation_bars"] for item in result["strategies"])


def test_strategy_comparison_rejects_insufficient_history():
    result = compare_strategies(make_candles(100))
    assert result["status"] == "insufficient_data"


def test_candle_order_is_normalized_and_duplicate_times_removed():
    candles = make_candles(420)
    candles = list(reversed(candles + [candles[-1]]))
    result = compare_strategies(candles)
    assert result["status"] == "ok"
    assert result["candles"] == 420


def test_metrics_are_finite_or_explicitly_unavailable():
    result = compare_strategies(make_candles())
    for item in result["strategies"]:
        assert np.isfinite(item["total_return_pct"])
        assert np.isfinite(item["max_drawdown_pct"])
        assert item["profit_factor"] is None or item["profit_factor"] == "infinite" or np.isfinite(item["profit_factor"])
        assert item["trades_evaluated"] >= 0
