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


from learning.confidence_gate import ModelPromotionGate, PromotionGateCriteria, select_confidence_threshold


def test_confidence_threshold_is_selected_from_prior_calibration_results():
    probabilities = np.array([0.91, 0.88, 0.82, 0.78, 0.73, 0.69] * 8)
    forward_returns = np.array([0.02, 0.01, 0.015, -0.01, -0.02, -0.015] * 8)
    result = select_confidence_threshold(probabilities, forward_returns, min_trades=5)
    assert result["status"] == "selected_from_historical_calibration"
    assert result["threshold"] in [row["threshold"] for row in result["candidate_results"]]
    assert result["calibration_samples"] == len(probabilities)


def test_confidence_filter_disables_trading_when_calibration_is_insufficient():
    result = select_confidence_threshold([0.51, 0.52, 0.49], [0.01, -0.01, 0.02], min_trades=10)
    assert result["threshold"] > 1.0
    assert result["status"] != "selected_from_historical_calibration"


def test_promotion_gate_fails_closed_for_insufficient_samples_or_folds():
    gate = ModelPromotionGate(PromotionGateCriteria(min_samples=100, min_folds=3, min_mean_f1=0.5))
    model = {"valid": True, "passes_threshold": True, "folds": [], "aggregated": {"mean_f1": 0.9}}
    result = gate.evaluate({"ensemble_passes": True, "rf": model, "xgb": model}, sample_count=50)
    assert result["passes"] is False
    assert result["failure_reasons"]


def test_promotion_gate_accepts_only_nonoverlapping_stable_folds():
    folds = [{"f1_macro": 0.7, "train_end_index": 99, "test_start_index": 100} for _ in range(3)]
    model = {"valid": True, "passes_threshold": True, "folds": folds, "aggregated": {"mean_f1": 0.7}}
    result = ModelPromotionGate(PromotionGateCriteria(min_samples=100, min_folds=3, min_mean_f1=0.5)).evaluate({"ensemble_passes": True, "rf": model, "xgb": model}, sample_count=200)
    assert result["passes"] is True
