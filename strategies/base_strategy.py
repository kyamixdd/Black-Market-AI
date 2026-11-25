"""Base class for all market intelligence strategies."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import numpy as np


class BaseStrategy(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def analyze(self, symbol: str, market: str, ohlc_data: dict[str, dict[str, np.ndarray]]) -> dict[str, Any] | None:
        """Perform analysis and return a signal if found.

        ohlc_data: { "1m": {"close": np.array, ...}, "5m": ... }
        """

    def _make_signal(self, symbol: str, market: str, direction: str,
                     timeframe: str, entry: float, stop_loss: float,
                     take_profit: list[float], score: float,
                     reasons: list[str]) -> dict[str, Any]:
        return {
            "signal_id": f"SIG-{uuid.uuid4().hex[:8].upper()}-{datetime.now(timezone.utc).strftime('%H%M%S')}",
            "symbol": symbol,
            "market": market,
            "strategy": self.name,
            "direction": direction,
            "timeframe": timeframe,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "raw_score": score,
            "reasons": reasons,
            "created_at": datetime.now(timezone.utc),
        }