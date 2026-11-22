"""Tests for deterministic Stage 17 market regime radar."""
import math

import pytest

from market.regime_radar import classify_market_regime


def candles_from_closes(closes, volume=100.0):
    rows = []
    for i, close in enumerate(closes):
        previous = closes[i - 1] if i else close
        rows.append({
            "open_time": i * 60_000, "close_time": (i + 1) * 60_000 - 1,
            "open": previous, "high": max(previous, close) * 1.001,
            "low": min(previous, close) * 0.999, "close": close,
            "volume": volume,
        })
    return rows


def test_insufficient_candles_are_explicit_and_no_confidence_claim():
    result = classify_market_regime(
        candles_from_closes([100 + i * 0.1 for i in range(30)]),
        symbol="BTCUSDT", market="SPOT", timeframe="1h",
    )
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["regime"] == "INSUFFICIENT_DATA"
    assert result["classification_confidence"] is None
    assert result["data_completeness"] == pytest.approx(0.3)


def test_uptrend_classification_contains_rule_evidence():
    closes = [100 * (1.002 ** i) for i in range(100)]
    result = classify_market_regime(
        candles_from_closes(closes), symbol="BTCUSDT",
        market="SPOT", timeframe="1h",
    )
    assert result["regime"] == "UPTREND"
    assert result["status"] == "READY"
    assert result["supporting_indicators"]["sma20"] > result["supporting_indicators"]["sma50"]
    assert result["evidence"]
    assert result["confidence_type"] == "not_statistically_calibrated"
    assert "not a prediction" in result["limitations"][0].lower()


def test_invalid_ohlcv_rows_are_excluded_and_completeness_reflects_valid_sample():
    rows = candles_from_closes([100 + i * 0.1 for i in range(60)])
    rows[5]["close"] = float("nan")
    rows[10]["volume"] = -1
    result = classify_market_regime(
        rows, symbol="ETHUSDT", market="SPOT", timeframe="15m",
        expected_candles=100,
    )
    assert result["sample_count"] == 58
    assert result["data_completeness"] == pytest.approx(0.58)
    assert result["status"] == "READY"


def test_constant_price_is_low_volatility_not_uptrend():
    result = classify_market_regime(
        candles_from_closes([100.0] * 100), symbol="BTCUSDT",
        market="SPOT", timeframe="1h",
    )
    assert result["regime"] == "LOW_VOLATILITY"
    assert result["supporting_indicators"]["realized_volatility_20_candles_pct"] == pytest.approx(0)


def test_classification_does_not_return_probability_confidence():
    closes = [100 * (1.001 ** i) for i in range(100)]
    result = classify_market_regime(
        candles_from_closes(closes), symbol="BTCUSDT",
        market="SPOT", timeframe="4h",
    )
    assert result["classification_confidence"] is None
    assert result["confidence_type"] == "not_statistically_calibrated"
