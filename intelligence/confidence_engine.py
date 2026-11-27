"""Confidence calculation based on signal features and market context."""
from __future__ import annotations

from typing import Any

_REGIME_BONUS: dict[str, float] = {
    "BULL_TREND": 0.15,
    "BEAR_TREND": 0.15,
    "SIDEWAYS": 0.05,
    "CONSOLIDATING": 0.08,
    "VOLATILE": 0.0,
    "UNKNOWN": 0.0,
}


class ConfidenceEngine:
    def calculate(self, signal: dict[str, Any]) -> float:
        """Score signal confidence from 0 to 1."""
        score = signal.get("raw_score", 50.0) / 100.0
        # Weighting factors
        weights = {
            "score": 0.6,
            "risk_reward": 0.2,
            "market_regime": 0.2,
        }
        # Risk Reward Ratio — guard against empty / None take_profit (I-1)
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tp_list = signal.get("take_profit") or [0]
        tp = tp_list[0]
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0
        rr_score = min(1.0, rr / 3.0)  # capped at 3:1 RR
        # Market regime contribution — actually use the declared weight (I-2)
        regime = signal.get("regime", "UNKNOWN")
        regime_score = _REGIME_BONUS.get(regime, 0.0) / 0.15  # normalise to [0,1]
        # Final weighted confidence
        conf = (
            (score * weights["score"])
            + (rr_score * weights["risk_reward"])
            + (regime_score * weights["market_regime"])
        )
        return min(1.0, conf)