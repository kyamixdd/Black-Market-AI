"""Market regime detection (trending, sideways, volatile)."""
from __future__ import annotations

import numpy as np

from .momentum_analyzer import MomentumAnalyzer
from .volatility_analyzer import VolatilityAnalyzer


class RegimeDetector:
    @staticmethod
    def detect(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> str:
        if len(closes) < 100:
            return "UNKNOWN"
        # ADX would be better, but simple slope + volatility works for baseline
        sma50 = MomentumAnalyzer.sma(closes, 50)
        price = closes[-1]
        bb = VolatilityAnalyzer.bollinger_bands(closes, 20, 2.0)
        bw = bb["bandwidth"]
        if bw < 0.01:
            return "CONSOLIDATING"
        if len(closes) >= 200:
            sma200 = MomentumAnalyzer.sma(closes, 200)
            if price > sma50 > sma200:
                return "BULL_TREND"
            if price < sma50 < sma200:
                return "BEAR_TREND"
        else:
            sma50_prior = MomentumAnalyzer.sma(closes[:-10], 50)
            if price > sma50 > sma50_prior:
                return "BULL_TREND"
            if price < sma50 < sma50_prior:
                return "BEAR_TREND"
        if bw > 0.05:
            return "VOLATILE"
        return "SIDEWAYS"

    @staticmethod
    def volatility_regime(closes: np.ndarray, window: int = 50) -> str:
        if len(closes) < window * 2:
            return "NORMAL"
        recent = closes[-window:]
        prior = closes[-window * 2:-window]
        r_vol = np.std(recent) / np.mean(recent) if np.mean(recent) > 0 else 0.0
        p_vol = np.std(prior) / np.mean(prior) if np.mean(prior) > 0 else 0.0
        if r_vol > p_vol * 1.5:
            return "EXPANDING"
        if r_vol < p_vol * 0.7:
            return "CONTRACTING"
        return "NORMAL"