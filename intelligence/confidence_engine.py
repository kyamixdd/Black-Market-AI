"""Confidence calculation based on signal features and market context."""
from __future__ import annotations

from typing import Any


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
        # Risk Reward Ratio
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", [0])[0]
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0
        rr_score = min(1.0, rr / 3.0)  # capped at 3:1 RR
        # Final weighted confidence
        conf = (score * weights["score"]) + (rr_score * weights["risk_reward"]) + (0.1)  # base
        return min(1.0, conf)