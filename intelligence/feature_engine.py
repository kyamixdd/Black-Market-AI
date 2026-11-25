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
                features.extend([0.0] * 9)
                continue
            data = ohlc_data[tf]
            closes = data["close"]
            highs = data["high"]
            lows = data["low"]
            volumes = data["volume"]
            if len(closes) < 20:
                features.extend([0.0] * 9)
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
            features.extend([
                rsi / 100.0,
                macd["hist"],
                bb_pos,
                min(1.0, atr / price) if price > 0 else 0.0,
                vol_exp,
                1.0 if vol_trend == "RISING" else (0.0 if vol_trend == "FALLING" else 0.5),
                returns_5,
                float(macd["macd"] > macd["signal"]),
                float(MomentumAnalyzer.sma(closes, 20) > MomentumAnalyzer.sma(closes, 50)),
            ])
        return np.array(features, dtype=np.float32)
