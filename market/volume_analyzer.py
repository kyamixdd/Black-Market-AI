"""Volume and liquidity analysis."""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class VolumeAnalyzer:
    @staticmethod
    def avg_volume(volumes: np.ndarray, window: int = 20) -> float:
        if len(volumes) < window:
            return float(np.mean(volumes)) if len(volumes) else 0.0
        return float(np.mean(volumes[-window:]))

    @staticmethod
    def volume_expansion(volumes: np.ndarray, window: int = 20, threshold: float = 1.5) -> bool:
        if len(volumes) < window + 1:
            return False
        avg = np.mean(volumes[-window - 1:-1])
        latest = volumes[-1]
        if avg <= 0:
            return False
        return latest > avg * threshold

    @staticmethod
    def volume_trend(volumes: np.ndarray, window: int = 10) -> str:
        if len(volumes) < window:
            return "UNKNOWN"
        recent = volumes[-window:]
        first_half = np.mean(recent[:window // 2])
        second_half = np.mean(recent[window // 2:])
        if first_half <= 0:
            return "FLAT"
        ratio = second_half / first_half
        if ratio > 1.3:
            return "RISING"
        if ratio < 0.7:
            return "FALLING"
        return "FLAT"

    @staticmethod
    def recent_trade_activity(trades: list[dict], window_seconds: int = 60) -> float:
        if not trades:
            return 0.0
        now = trades[-1].get("time", 0)
        total = 0.0
        for t in reversed(trades):
            if now - t.get("time", 0) > window_seconds * 1000:
                break
            total += float(t.get("qty", 0)) * float(t.get("price", 0))
        return total

    @staticmethod
    def vwap(closes: np.ndarray, volumes: np.ndarray, period: int = 20) -> float:
        """Volume Weighted Average Price."""
        if len(closes) < period or len(volumes) < period:
            return float(closes[-1]) if len(closes) else 0.0
        recent_closes = closes[-period:]
        recent_volumes = volumes[-period:]
        vol_sum = np.sum(recent_volumes)
        if vol_sum <= 0:
            return float(closes[-1])
        return float(np.sum(recent_closes * recent_volumes) / vol_sum)