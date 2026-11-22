"""Deterministic regression tests for Stage 5 analytics."""
import math

import numpy as np

from market.analytics import (
    breadth_summary, historical_volatility, price_change,
    return_correlation, volume_comparison,
)


def test_historical_volatility_requires_25_hourly_closes_and_is_reproducible():
    closes = [100 * (1.01 ** index) for index in range(25)]
    expected = math.sqrt(24 * math.log(1.01) ** 2) * 100
    assert historical_volatility(closes, 24) == pytest.approx(expected)
    assert historical_volatility(closes[:24], 24) is None
    assert historical_volatility([100, 101, 0, 102], 2) is None


def test_volume_comparison_uses_prior_baseline_and_handles_zero_volume():
    result = volume_comparison([10] * 20 + [20], 20)
    assert result["status"] == "READY"
    assert result["average"] == 10
    assert result["change_pct"] == 100
    assert volume_comparison([0] * 21, 20)["status"] == "ZERO_BASELINE"
    assert volume_comparison([1, 2], 20)["status"] == "INSUFFICIENT_DATA"
    assert volume_comparison([1] * 20 + [float("nan")], 20)["status"] == "INVALID_DATA"


def test_price_change_exact_period_boundary_and_invalid_data():
    assert price_change([100, 110, 121], 2) == pytest.approx(21)
    assert price_change([100, 110], 2) is None
    assert price_change([100, 0, 121], 2) is None


def test_return_correlation_aligned_returns_and_constant_series():
    left = [100 * (1.01 ** i) for i in range(30)]
    right = [50 * (1.01 ** i) for i in range(30)]
    assert return_correlation(left, right, minimum_returns=20) == pytest.approx(1.0)
    assert return_correlation(left[:15], right[:15], minimum_returns=20) is None
    assert return_correlation(left, [50] * 30, minimum_returns=20) is None


def test_breadth_sample_counts_only_advancing_declining_neutral():
    result = breadth_summary([1.0, -2.0, 0.0, float("nan")])
    assert result["sample_size"] == 3
    assert result["advancing"] == result["declining"] == result["neutral"] == 1
    assert result["advance_decline_ratio"] == 1
    assert breadth_summary([])["status"] == "UNAVAILABLE"


import pytest
