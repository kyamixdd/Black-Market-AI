"""Breakout strategy: detect price escaping consolidation."""
from __future__ import annotations

from typing import Any

import numpy as np

from market.volatility_analyzer import VolatilityAnalyzer
from market.volume_analyzer import VolumeAnalyzer
from strategies.base_strategy import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("breakout")

    def analyze(self, symbol: str, market: str, ohlc_data: dict[str, dict[str, np.ndarray]]) -> dict[str, Any] | None:
        tf = "15m"
        if tf not in ohlc_data:
            return None
        data = ohlc_data[tf]
        closes = data["close"]
        highs = data["high"]
        lows = data["low"]
        volumes = data["volume"]
        if len(closes) < 30:
            return None
        # Check consolidation window
        lookback = 20
        recent_highs = highs[-lookback - 1:-1]
        recent_lows = lows[-lookback - 1:-1]
        res = float(np.max(recent_highs))
        sup = float(np.min(recent_lows))
        latest = float(closes[-1])
        volume_expanded = VolumeAnalyzer.volume_expansion(volumes, 20, 1.3)
        # Bullish breakout
        if latest > res and volume_expanded:
            atr = VolatilityAnalyzer.atr(highs, lows, closes, 14)
            if atr <= 0:
                return None
            sl = res - atr
            tp = [latest + (atr * 2.5), latest + (atr * 5.0)]
            return self._make_signal(symbol, market, "LONG", tf, latest, sl, tp, 85.0,
                                     ["Resistance breakout", "Volume expansion confirmed"])
        # Bearish breakout
        if latest < sup and volume_expanded:
            atr = VolatilityAnalyzer.atr(highs, lows, closes, 14)
            if atr <= 0:
                return None
            sl = sup + atr
            tp = [latest - (atr * 2.5), latest - (atr * 5.0)]
            return self._make_signal(symbol, market, "SHORT" if market == "FUTURES" else "SELL",
                                     tf, latest, sl, tp, 85.0,
                                     ["Support breakout", "Volume expansion confirmed"])
        return None