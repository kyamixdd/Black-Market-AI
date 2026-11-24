"""Momentum strategy: identify accelerating price movement."""
from __future__ import annotations

from typing import Any

import numpy as np

from market.momentum_analyzer import MomentumAnalyzer
from market.volatility_analyzer import VolatilityAnalyzer
from strategies.base_strategy import BaseStrategy


class MomentumStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("momentum")

    def analyze(self, symbol: str, market: str, ohlc_data: dict[str, dict[str, np.ndarray]]) -> dict[str, Any] | None:
        # Focus on 15m as primary setup
        tf = "15m"
        if tf not in ohlc_data:
            return None
        data = ohlc_data[tf]
        closes = data["close"]
        if len(closes) < 30:
            return None
        rsi = MomentumAnalyzer.rsi(closes, 14)
        macd = MomentumAnalyzer.macd(closes)
        # Bullish momentum
        if rsi > 55 and macd["hist"] > 0 and macd["macd"] > macd["signal"]:
            entry = float(closes[-1])
            atr = VolatilityAnalyzer.atr(data["high"], data["low"], closes, 14)
            if atr <= 0:
                return None
            sl = entry - (atr * 2.0)
            tp = [entry + (atr * 2.0), entry + (atr * 4.0)]
            return self._make_signal(symbol, market, "LONG", tf, entry, sl, tp, rsi,
                                     ["RSI bullish", "MACD cross up", "Positive momentum"])
        # Bearish momentum
        if rsi < 45 and macd["hist"] < 0 and macd["macd"] < macd["signal"]:
            entry = float(closes[-1])
            atr = VolatilityAnalyzer.atr(data["high"], data["low"], closes, 14)
            if atr <= 0:
                return None
            sl = entry + (atr * 2.0)
            tp = [entry - (atr * 2.0), entry - (atr * 4.0)]
            return self._make_signal(symbol, market, "SHORT" if market == "FUTURES" else "SELL",
                                     tf, entry, sl, tp, 100 - rsi,
                                     ["RSI bearish", "MACD cross down", "Negative momentum"])
        return None