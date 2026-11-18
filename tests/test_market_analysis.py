"""Test market analysis components."""
import numpy as np

from market.regime_detector import RegimeDetector
from market.volatility_analyzer import VolatilityAnalyzer
from market.volume_analyzer import VolumeAnalyzer


def test_volatility_analyzer():
    closes = np.array([100.0, 101.0, 102.0, 101.0, 100.0])
    highs = closes + 0.5
    lows = closes - 0.5

    atr = VolatilityAnalyzer.atr(highs, lows, closes, period=3)
    assert atr > 0

    bb = VolatilityAnalyzer.bollinger_bands(closes, period=3)
    assert "middle" in bb
    assert bb["upper"] > bb["middle"] > bb["lower"]

def test_volume_analyzer():
    volumes = np.array([100.0, 100.0, 100.0, 100.0, 200.0])

    avg = VolumeAnalyzer.avg_volume(volumes, window=3)
    assert avg > 100.0

    expansion = VolumeAnalyzer.volume_expansion(volumes, window=3, threshold=1.5)
    assert expansion == True

    trend = VolumeAnalyzer.volume_trend(volumes, window=4)
    assert trend == "RISING"

def test_regime_detector():
    # Construct data for trends
    closes = np.linspace(100.0, 200.0, 250)
    highs = closes + 1.0
    lows = closes - 1.0

    regime = RegimeDetector.detect(closes, highs, lows)
    assert regime == "BULL_TREND"
