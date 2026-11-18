"""Feature engineering for ML models."""
from __future__ import annotations

import numpy as np

from market.momentum_analyzer import MomentumAnalyzer
from market.volatility_analyzer import VolatilityAnalyzer
from market.volume_analyzer import VolumeAnalyzer


class FeatureEngine:
    def build_features(self, symbol: str, market: str,
                       ohlc_data: dict[str, dict[str, np.ndarray]]) -> np.ndarray:
        """Build a feature vector from multi-timeframe data."""
        features = []
        # Timeframe priorities
        for tf in ["15m", "1h", "4h", "1d"]:
            if tf not in ohlc_data:
                features.extend([0.0] * 12)
                continue
            data = ohlc_data[tf]
            closes = data["close"]
            highs = data["high"]
            lows = data["low"]
            volumes = data["volume"]
            if len(closes) < 20:
                features.extend([0.0] * 12)
                continue
            price = closes[-1]
            rsi = MomentumAnalyzer.rsi(closes)
            macd = MomentumAnalyzer.macd(closes)
            bb = VolatilityAnalyzer.bollinger_bands(closes)
            atr = VolatilityAnalyzer.atr(highs, lows, closes)
            vol_trend = VolumeAnalyzer.volume_trend(volumes)
            vol_exp = 1.0 if VolumeAnalyzer.volume_expansion(volumes) else 0.0
            bb_pos = (price - bb["lower"]) / (bb["upper"] - bb["lower"]) if bb["upper"] > bb["lower"] else 0.5
            returns_5 = (price / closes[-6] - 1.0) if len(closes) >= 6 else 0.0
            sma_20 = MomentumAnalyzer.sma(closes, 20)
            sma_50 = MomentumAnalyzer.sma(closes, 50)
            returns_20 = (price / closes[-21] - 1.0) if len(closes) >= 21 and closes[-21] > 0 else 0.0
            candle_range = highs[-1] - lows[-1]
            close_location = (price - lows[-1]) / candle_range if candle_range > 0 else 0.5
            features.extend([
                rsi / 100.0,
                macd["hist"],
                bb_pos,
                min(1.0, atr / price) if price > 0 else 0.0,
                vol_exp,
                1.0 if vol_trend == "RISING" else (0.0 if vol_trend == "FALLING" else 0.5),
                returns_5,
                float(macd["macd"] > macd["signal"]),
                float(sma_20 > sma_50),
                returns_20,
                (price / sma_20 - 1.0) if sma_20 > 0 else 0.0,
                close_location,
            ])
        return np.array(features, dtype=np.float32)