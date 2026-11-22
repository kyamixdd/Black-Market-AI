"""Regression tests for confidence-threshold transaction-cost accounting."""
import pytest

from learning.confidence_gate import select_confidence_threshold


def _evaluate(returns, probabilities=None, *, fee_rate=0.0004, candidates=(0.5,)):
    probabilities = probabilities or [0.9] * len(returns)
    return select_confidence_threshold(
        probabilities,
        returns,
        fee_rate=fee_rate,
        candidates=candidates,
        min_trades=1,
    )["selected_metrics"]


def test_expectancy_includes_entry_and_terminal_exit_fee():
    metrics = _evaluate([0.0] * 10)

    # One entry and one terminal close: 2 * fee / 10 active periods.
    assert metrics["net_expectancy_per_trade"] == pytest.approx(-0.00008)
    assert metrics["net_return_pct"] == pytest.approx(-0.079984)


def test_exit_fee_is_attributed_to_last_active_period():
    metrics = _evaluate(
        [0.0] * 10,
        probabilities=[0.9, 0.9, 0.9, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4],
        candidates=(0.7,),
    )

    # The position closes at the first inactive row. That exit cost must not
    # disappear from the active-period expectancy.
    assert metrics["net_expectancy_per_trade"] == pytest.approx(-0.0002666666666666667)
    assert metrics["net_return_pct"] == pytest.approx(-0.079984)


def test_reversal_charges_close_and_reopen_fees():
    metrics = _evaluate(
        [0.0] * 10,
        probabilities=[0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
    )

    # Entry (1x), reversal (2x), terminal close (1x) = 4 fees.
    assert metrics["net_expectancy_per_trade"] == pytest.approx(-0.00016)



def test_heldout_test_set_does_not_choose_calibration_threshold():
    calibration = select_confidence_threshold(
        [0.9] * 20, [0.01] * 20, fee_rate=0.0,
        candidates=(0.6, 0.9), min_trades=1,
        test_probabilities=[0.9] * 20,
        test_forward_returns=[-0.01] * 20,
    )
    assert calibration["threshold"] == 0.6
    assert calibration["heldout_test_metrics"]["net_expectancy_per_trade"] == pytest.approx(-0.01)
    assert "evaluation-only" in calibration["calibration_test_boundary"]



def test_live_confidence_gate_blocks_low_confidence_prediction():
    from learning.confidence_gate import evaluate_live_confidence

    allowed, reason = evaluate_live_confidence(0.61, 0.72, "model-v1", "model-v1")
    assert not allowed
    assert reason == "below_historical_confidence_threshold"


@pytest.mark.parametrize(
    "confidence,threshold,model_version,calibrated_version",
    [
        (0.95, None, "model-v1", "model-v1"),
        (0.95, 0.70, "model-v1", "model-v0"),
        (0.95, 0.70, "untrained", "untrained"),
    ],
)
def test_live_confidence_gate_fails_closed_without_matching_calibration(
    confidence, threshold, model_version, calibrated_version
):
    from learning.confidence_gate import evaluate_live_confidence

    allowed, _ = evaluate_live_confidence(
        confidence, threshold, model_version, calibrated_version
    )
    assert not allowed


def _promotion_fixture(challenger_pred=2, champion_pred=0):
    from learning.confidence_gate import ModelPromotionGate, PromotionGateCriteria
    criteria = PromotionGateCriteria(min_samples=6, min_folds=3, min_mean_accuracy=0.5, min_mean_f1=0.5,
        max_fold_degradation=0.2, min_net_expectancy=0.0001, max_drawdown_pct=50.0,
        min_calibration_score=0.5, min_stability_score=0.0, min_regime_coverage=1,
        min_regime_samples=2, min_improvement_over_champion=0.02, min_net_expectancy_improvement=0.0001)
    folds = [
        {"f1_macro": 0.8, "train_end_index": 0, "test_start_index": 1, "test_end_index": 1},
        {"f1_macro": 0.8, "train_end_index": 1, "test_start_index": 2, "test_end_index": 3},
        {"f1_macro": 0.8, "train_end_index": 3, "test_start_index": 4, "test_end_index": 5},
    ]
    candidate_oof = [{"index": i, "y_true": 2, "y_pred": challenger_pred, "probabilities": [0.05, 0.05, 0.90]} for i in range(6)]
    champion_oof = [{"index": i, "y_true": 2, "y_pred": champion_pred, "probabilities": [0.80, 0.10, 0.10]} for i in range(6)]
    validation = {
        "rf": {"valid": True, "passes_threshold": True, "aggregated": {"mean_f1": 0.8, "mean_accuracy": 0.8}, "folds": folds, "out_of_fold": candidate_oof},
        "xgb": {"valid": True, "passes_threshold": True, "aggregated": {"mean_f1": 0.8, "mean_accuracy": 0.8}, "folds": folds, "out_of_fold": candidate_oof},
        "ensemble_passes": True,
    }
    champion = {name: {"valid": True, "passes_threshold": True, "aggregated": {"mean_f1": 0.4, "mean_accuracy": 0.4}, "folds": folds, "out_of_fold": champion_oof} for name in ("rf", "xgb")}
    metadata = {"timestamps": [1000, 2000, 3000, 4000, 5000, 6000], "actual_return_pct": [1.0] * 6, "transaction_costs": [0.0001] * 6,
        "regimes": ["TREND", "TREND", "RANGE", "RANGE", "VOLATILE", "VOLATILE"],
        "markets": ["SPOT"] * 6, "horizon_minutes": [60] * 6}
    return ModelPromotionGate(criteria), validation, champion, metadata


def test_comprehensive_promotion_gate_requires_cost_adjusted_champion_improvement():
    gate, validation, champion, metadata = _promotion_fixture()
    result = gate.evaluate(validation, 6, economic_metadata=metadata, champion_validation=champion)
    assert result["passes"] is True
    assert result["economic_evidence"]["rf"]["mean_fees_and_slippage"] == pytest.approx(0.0001)
    assert result["economic_evidence"]["rf"]["mean_funding_cost"] == 0.0
    assert result["economic_evidence"]["rf"]["relative_f1_improvement"] >= 0.02


def test_comprehensive_promotion_gate_fails_closed_without_cost_or_champion_data():
    gate, validation, _champion, _metadata = _promotion_fixture()
    result = gate.evaluate(validation, 6)
    assert result["passes"] is False
    assert any("evidence unavailable" in reason for reason in result["failure_reasons"])
    assert any("active champion comparison evidence missing" in reason for reason in result["failure_reasons"])


def test_comprehensive_promotion_gate_rejects_negative_net_expectancy():
    gate, validation, champion, metadata = _promotion_fixture(challenger_pred=0, champion_pred=2)
    result = gate.evaluate(validation, 6, economic_metadata=metadata, champion_validation=champion)
    assert result["passes"] is False
    assert any("net expectancy" in reason for reason in result["failure_reasons"])
