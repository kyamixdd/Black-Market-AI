"""Adaptive strategy selector: weights strategies by regime and performance."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class StrategySelector:
    def __init__(self):
        self.weights = {
            "momentum": 1.0,
            "breakout": 1.0,
            "trend_following": 1.0,
            "mean_reversion": 1.0,
            "reversal": 1.0,
        }
        self.regime_prefs = {
            "BULL_TREND": {"trend_following": 1.5, "momentum": 1.2, "breakout": 1.1},
            "BEAR_TREND": {"trend_following": 1.5, "momentum": 1.2, "breakout": 1.1},
            "SIDEWAYS": {"mean_reversion": 1.5, "reversal": 1.2},
            "CONSOLIDATING": {"breakout": 1.5, "mean_reversion": 1.2},
            "VOLATILE": {"reversal": 1.2, "mean_reversion": 1.1},
        }

    def get_weight(self, strategy: str, regime: str | None = None) -> float:
        w = self.weights.get(strategy, 1.0)
        if regime and regime in self.regime_prefs:
            w *= self.regime_prefs[regime].get(strategy, 1.0)
        return w

    def update_performance(self, strategy: str, win: bool, pnl_pct: float) -> None:
        self.weights.setdefault(strategy, 1.0)
        if win:
            self.weights[strategy] = min(2.0, self.weights[strategy] * 1.02)
        else:
            self.weights[strategy] = max(0.2, self.weights[strategy] * 0.98)
        logger.debug("Strategy %s weight updated to %.3f", strategy, self.weights[strategy])