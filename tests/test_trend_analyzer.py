"""Test multi-timeframe trend analysis."""
import numpy as np

from market.candle_manager import CandleManager
from market.momentum_analyzer import MomentumAnalyzer
from market.trend_analyzer import TrendAnalyzer
from market.volume_analyzer import VolumeAnalyzer


def test_adx():
    highs = np.array([102.0, 103.0, 104.0, 105.0, 106.0, 107.0])
    lows = np.array([98.0, 99.0, 100.0, 101.0, 102.0, 103.0])
    closes = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])

    adx = MomentumAnalyzer.adx(highs, lows, closes, period=3)
    assert "adx" in adx
    assert "plus_di" in adx
    assert "minus_di" in adx
    assert adx["adx"] >= 0

def test_vwap():
    closes = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    volumes = np.array([100.0, 100.0, 100.0, 100.0, 100.0])

    vwap = VolumeAnalyzer.vwap(closes, volumes, period=3)
    assert vwap > 100.0

def test_candle_deduplication():
    cm = CandleManager()

    # Add first candle
    added = cm.add_candle("SPOT", "BTCUSDT", "1m", 1000, 100.0, 101.0, 99.0, 100.5, 1000.0)
    assert added is True

    # Try to add duplicate (same open_time)
    added = cm.add_candle("SPOT", "BTCUSDT", "1m", 1000, 100.0, 101.0, 99.0, 100.5, 1000.0)
    assert added is False

    # Add new candle
    added = cm.add_candle("SPOT", "BTCUSDT", "1m", 1060, 100.5, 102.0, 100.0, 101.5, 1100.0)
    assert added is True

def test_trend_analyzer():
    cm = CandleManager()
    analyzer = TrendAnalyzer(cm)

    # Add sufficient data for multiple timeframes
    base_time = 1000000
    for i in range(100):
        t = base_time + i * 60000
        price = 100.0 + i * 0.1
        cm.add_candle("SPOT", "BTCUSDT", "1m", t, price, price + 0.5, price - 0.5, price + 0.1, 1000.0)

    result = analyzer.analyze("SPOT", "BTCUSDT")
    assert "1m" in result
    assert "alignment" in result

def test_candle_manager_deduplicates_overlapping_historical_refreshes():
    cm = CandleManager()
    candles = [(1000, 10.0), (61000, 11.0), (121000, 12.0)]
    for timestamp, close in candles:
        assert cm.add_candle("SPOT", "BTCUSDT", "1m", timestamp, close, close, close, close, 1.0)

    # Replaying older history must update in place, not append it to the tail.
    assert cm.add_candle("SPOT", "BTCUSDT", "1m", 61000, 11.0, 11.5, 10.5, 11.2, 2.0) is False
    series = cm.get_series("SPOT", "BTCUSDT", "1m", limit=10)
    assert [c["open_time"] for c in series] == [1000, 61000, 121000]
    assert series[1]["close"] == 11.2

    # A genuinely new candle remains in chronological order.
    assert cm.add_candle("SPOT", "BTCUSDT", "1m", 181000, 13.0, 13.0, 13.0, 13.0, 1.0)
    assert [c["open_time"] for c in cm.get_series("SPOT", "BTCUSDT", "1m", limit=10)] == [
        1000, 61000, 121000, 181000
    ]
