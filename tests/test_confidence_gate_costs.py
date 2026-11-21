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
