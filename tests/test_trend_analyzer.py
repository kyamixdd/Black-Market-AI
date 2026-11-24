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