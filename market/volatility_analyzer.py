"""Volatility analysis (ATR, Bollinger Bands)."""
from __future__ import annotations

import numpy as np


class VolatilityAnalyzer:
    @staticmethod
    def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.0
        tr_list = []
        for i in range(1, len(closes)):
            h = highs[i]
            l = lows[i]
            cp = closes[i - 1]
            tr = max(h - l, abs(h - cp), abs(l - cp))
            tr_list.append(tr)
        if len(tr_list) < period:
            return float(np.mean(tr_list)) if tr_list else 0.0
        atr_val = float(np.mean(tr_list[:period]))
        for tr in tr_list[period:]:
            atr_val = (atr_val * (period - 1) + float(tr)) / period
        return float(atr_val)

    @staticmethod
    def bollinger_bands(closes: np.ndarray, period: int = 20, std_devs: float = 2.0) -> dict[str, float]:
        if len(closes) < period:
            c = closes[-1] if len(closes) else 0.0
            return {"middle": float(c), "upper": float(c), "lower": float(c), "bandwidth": 0.0}
        recent = closes[-period:]
        mid = float(np.mean(recent))
        sd = float(np.std(recent))
        upper = mid + std_devs * sd
        lower = mid - std_devs * sd
        bw = (upper - lower) / mid if mid > 0 else 0.0
        return {
            "middle": mid,
            "upper": upper,
            "lower": lower,
            "bandwidth": bw,
        }