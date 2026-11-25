"""Order book analysis for liquidity and imbalance signals."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class OrderBookAnalyzer:
    @staticmethod
    def imbalance(depth: dict, levels: int = 10) -> float:
        bids = depth.get("bids", [])[:levels]
        asks = depth.get("asks", [])[:levels]
        bid_volume = sum(float(b[1]) for b in bids)
        ask_volume = sum(float(a[1]) for a in asks)
        total = bid_volume + ask_volume
        if total <= 0:
            return 0.0
        return (bid_volume - ask_volume) / total

    @staticmethod
    def spread(depth: dict) -> float | None:
        bids = depth.get("bids", [])
        asks = depth.get("asks", [])
        if not bids or not asks:
            return None
        try:
            bid = float(bids[0][0])
            ask = float(asks[0][0])
            return (ask - bid) / ask if ask > 0 else None
        except (TypeError, ValueError, IndexError):
            return None