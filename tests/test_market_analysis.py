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


def test_regime_detector_handles_between_100_and_200_candles():
    closes = np.linspace(100.0, 200.0, 150)
    highs = closes + 1.0
    lows = closes - 1.0
    assert RegimeDetector.detect(closes, highs, lows) == "BULL_TREND"
    assert RegimeDetector.detect(closes[::-1], highs[::-1], lows[::-1]) == "BEAR_TREND"


def test_data_integrity_guardian_recovers_after_fresh_candles():
    from market.candle_manager import CandleManager
    from market.data_integrity import DataIntegrityGuardian

    cm = CandleManager()
    guardian = DataIntegrityGuardian(cm)
    now_ms = cm.current_time_ms()
    # Seed stale candles first
    stale_end = now_ms - 10_000_000
    for i in range(25):
        open_t = stale_end - (25 - i) * 3_600_000
        cm.add_candle("SPOT", "BTCUSDT", "1h", open_t, 100.0, 101.0, 99.0, 100.5, 10.0, open_t + 3_599_999)
    assert guardian.is_symbol_valid("SPOT", "BTCUSDT") is False

    # Now add fresh continuous candles up to now
    base = now_ms - 25 * 3_600_000
    for i in range(25):
        open_t = base + i * 3_600_000
        cm.add_candle("SPOT", "BTCUSDT", "1h", open_t, 100.0, 101.0, 99.0, 100.5, 10.0, open_t + 3_599_999)
    assert guardian.is_symbol_valid("SPOT", "BTCUSDT") is True
