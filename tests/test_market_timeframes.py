"""Regression tests for chart and candle interval support."""

from market.candle_manager import TIMEFRAME_SECONDS


def test_market_candle_manager_supports_all_chart_intervals():
    expected_seconds = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "6h": 21600,
        "12h": 43200,
        "1d": 86400,
        "1w": 604800,
    }

    assert TIMEFRAME_SECONDS == expected_seconds
