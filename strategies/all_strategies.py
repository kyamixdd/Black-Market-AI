"""Trend Following, Mean Reversion, and Reversal strategies."""
from __future__ import annotations

from typing import Any

import numpy as np

from market.momentum_analyzer import MomentumAnalyzer
from market.volatility_analyzer import VolatilityAnalyzer
from strategies.base_strategy import BaseStrategy


class TrendFollowingStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("trend_following")

    def analyze(self, symbol: str, market: str, ohlc_data: dict[str, dict[str, np.ndarray]]) -> dict[str, Any] | None:
        tf = "1h"
        if tf not in ohlc_data:
            return None
        data = ohlc_data[tf]
        closes = data["close"]
        if len(closes) < 50:
            return None
        sma20 = MomentumAnalyzer.sma(closes, 20)
        sma50 = MomentumAnalyzer.sma(closes, 50)
        price = float(closes[-1])
        atr = VolatilityAnalyzer.atr(data["high"], data["low"], closes, 14)
        if atr <= 0:
            return None
        if price > sma20 > sma50:
            sl = sma20 - atr
            tp = [price + (atr * 3.0), price + (atr * 6.0)]
            return self._make_signal(symbol, market, "LONG", tf, price, sl, tp, 80.0,
                                     ["Uptrend structure", "MA alignment (20 > 50)"])
        if price < sma20 < sma50:
            sl = sma20 + atr
            tp = [price - (atr * 3.0), price - (atr * 6.0)]
            return self._make_signal(symbol, market, "SHORT" if market == "FUTURES" else "SELL",
                                     tf, price, sl, tp, 80.0,
                                     ["Downtrend structure", "MA alignment (20 < 50)"])
        return None


class MeanReversionStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("mean_reversion")

    def analyze(self, symbol: str, market: str, ohlc_data: dict[str, dict[str, np.ndarray]]) -> dict[str, Any] | None:
        tf = "15m"
        if tf not in ohlc_data:
            return None
        data = ohlc_data[tf]
        closes = data["close"]
        if len(closes) < 20:
            return None
        bb = VolatilityAnalyzer.bollinger_bands(closes, 20, 2.0)
        rsi = MomentumAnalyzer.rsi(closes, 14)
        price = float(closes[-1])
        if price <= bb["lower"] and rsi < 30:
            sl = price * 0.985
            tp = [bb["middle"], bb["upper"]]
            return self._make_signal(symbol, market, "LONG", tf, price, sl, tp, 75.0,
                                     ["Oversold BB lower touch", f"RSI low ({rsi:.1f})"])
        if price >= bb["upper"] and rsi > 70:
            sl = price * 1.015
            tp = [bb["middle"], bb["lower"]]
            return self._make_signal(symbol, market, "SHORT" if market == "FUTURES" else "SELL",
                                     tf, price, sl, tp, 75.0,
                                     ["Overbought BB upper touch", f"RSI high ({rsi:.1f})"])
        return None


class ReversalStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("reversal")

    def analyze(self, symbol: str, market: str, ohlc_data: dict[str, dict[str, np.ndarray]]) -> dict[str, Any] | None:
        tf = "15m"
        if tf not in ohlc_data:
            return None
        data = ohlc_data[tf]
        closes = data["close"]
        if len(closes) < 30:
            return None
        rsi = MomentumAnalyzer.rsi(closes, 14)
        price = float(closes[-1])
        # Divergence check heuristic
        if rsi < 25:
            sl = price * 0.98
            tp = [price * 1.03, price * 1.06]
            return self._make_signal(symbol, market, "LONG", tf, price, sl, tp, 70.0,
                                     ["Extreme oversold reversal potential"])
        if rsi > 75:
            sl = price * 1.02
            tp = [price * 0.97, price * 0.94]
            return self._make_signal(symbol, market, "SHORT" if market == "FUTURES" else "SELL",
                                     tf, price, sl, tp, 70.0,
                                     ["Extreme overbought reversal potential"])
        return None