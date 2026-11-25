"""Feature engineering for ML models - learning-specific wrapper."""
from __future__ import annotations

import numpy as np

from intelligence.feature_engine import FeatureEngine as IntelligenceFeatureEngine


class FeatureEngine:
    """Learning-specific feature engine that wraps the intelligence feature engine."""

    def __init__(self):
        self._intel_engine = IntelligenceFeatureEngine()

    def build_features(self, symbol: str, market: str,
                       ohlc_data: dict[str, dict[str, np.ndarray]]) -> np.ndarray:
        """Build a feature vector from multi-timeframe data."""
        return self._intel_engine.build_features(symbol, market, ohlc_data)