"""Momentum and technical indicator calculation."""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class MomentumAnalyzer:
    @staticmethod
    def rsi(closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        diff = np.diff(closes)
        gains = np.where(diff > 0, diff, 0.0)
        losses = np.where(diff < 0, -diff, 0.0)
        avg_gain = float(np.mean(gains[:period]))
        avg_loss = float(np.mean(losses[:period]))
        for idx in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + float(gains[idx])) / period
            avg_loss = (avg_loss * (period - 1) + float(losses[idx])) / period
        if avg_gain == 0 and avg_loss == 0:
            return 50.0
        if avg_loss == 0:
            return 100.0
        if avg_gain == 0:
            return 0.0
        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    @staticmethod
    def macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float]:
        if len(closes) < slow + signal:
            return {"macd": 0.0, "signal": 0.0, "hist": 0.0}

        def ema(data, window):
            # Recursive EMA keeps the newest observations most influential and
            # avoids the truncated-convolution edge effect on short histories.
            values = np.asarray(data, dtype=float)
            alpha = 2.0 / (window + 1.0)
            result = np.empty_like(values, dtype=float)
            result[0] = values[0]
            for index in range(1, len(values)):
                result[index] = alpha * values[index] + (1.0 - alpha) * result[index - 1]
            return result

        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        macd_line = ema_fast - ema_slow
        sig_line = ema(macd_line, signal)
        hist = macd_line - sig_line
        return {
            "macd": float(macd_line[-1]),
            "signal": float(sig_line[-1]),
            "hist": float(hist[-1]),
        }

    @staticmethod
    def sma(closes: np.ndarray, period: int) -> float:
        if len(closes) < period:
            return float(closes[-1]) if len(closes) else 0.0
        return float(np.mean(closes[-period:]))

    @staticmethod
    def ema(closes: np.ndarray, period: int) -> float:
        if len(closes) < period:
            return float(closes[-1]) if len(closes) else 0.0
        values = np.asarray(closes, dtype=float)
        alpha = 2.0 / (period + 1.0)
        ema_val = float(np.mean(values[:period]))
        for price in values[period:]:
            ema_val = alpha * float(price) + (1.0 - alpha) * ema_val
        return float(ema_val)

    @staticmethod
    def adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
            period: int = 14) -> dict[str, float]:
        """Wilder-smoothed ADX and directional indicators."""
        if period < 2 or len(closes) < period * 2 + 1 or len(highs) != len(closes) or len(lows) != len(closes):
            return {"adx": 0.0, "plus_di": 0.0, "minus_di": 0.0}
        tr, plus_dm, minus_dm = [], [], []
        for index in range(1, len(closes)):
            high, low, previous_close = highs[index], lows[index], closes[index - 1]
            tr.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
            up = highs[index] - highs[index - 1]
            down = lows[index - 1] - lows[index]
            plus_dm.append(up if up > down and up > 0 else 0.0)
            minus_dm.append(down if down > up and down > 0 else 0.0)
        tr = np.asarray(tr, dtype=float)
        plus_dm = np.asarray(plus_dm, dtype=float)
        minus_dm = np.asarray(minus_dm, dtype=float)
        if not all(np.isfinite(array).all() for array in (tr, plus_dm, minus_dm)) or (tr < 0).any():
            return {"adx": 0.0, "plus_di": 0.0, "minus_di": 0.0}
        smooth_tr = float(np.sum(tr[:period]))
        smooth_plus = float(np.sum(plus_dm[:period]))
        smooth_minus = float(np.sum(minus_dm[:period]))
        dx_values = []
        last_plus = last_minus = 0.0
        for index in range(period - 1, len(tr)):
            if index > period - 1:
                smooth_tr = smooth_tr - smooth_tr / period + tr[index]
                smooth_plus = smooth_plus - smooth_plus / period + plus_dm[index]
                smooth_minus = smooth_minus - smooth_minus / period + minus_dm[index]
            if smooth_tr <= 0:
                dx_values.append(0.0)
                continue
            last_plus = 100.0 * smooth_plus / smooth_tr
            last_minus = 100.0 * smooth_minus / smooth_tr
            denominator = last_plus + last_minus
            dx_values.append(100.0 * abs(last_plus - last_minus) / denominator if denominator > 0 else 0.0)
        if len(dx_values) < period:
            return {"adx": 0.0, "plus_di": float(last_plus), "minus_di": float(last_minus)}
        adx = float(np.mean(dx_values[:period]))
        for value in dx_values[period:]:
            adx = ((adx * (period - 1)) + value) / period
        return {"adx": adx, "plus_di": float(last_plus), "minus_di": float(last_minus)}
