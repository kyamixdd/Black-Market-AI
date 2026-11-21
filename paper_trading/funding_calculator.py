"""Futures funding payment calculation."""
from __future__ import annotations

import math


class FundingCalculator:
    # Binance funding intervals: every 8 hours (00:00, 08:00, 16:00 UTC)
    FUNDING_INTERVAL_HOURS = 8

    def calculate(self, position: dict, funding_rate: float, mark_price: float | None = None) -> float:
        """Calculate funding payment for a futures position.

        Positive funding rate = longs pay shorts
        Negative funding rate = shorts pay longs
        """
        if position["market"] != "FUTURES":
            return 0.0
        # Funding is charged on the position's current notional value, not
        # the initial margin. Leverage changes required margin, not the
        # quantity of underlying exposure being funded.
        funding_price = mark_price if mark_price is not None else (position.get("current_price") or position["entry_price"])
        funding_price = float(funding_price)
        if not math.isfinite(funding_price) or funding_price <= 0:
            raise ValueError("Funding mark price must be finite and positive.")
        notional = float(position["amount"]) * funding_price
        if position["side"] in ("LONG", "BUY"):
            return notional * float(funding_rate)
        if position["side"] in ("SHORT", "SELL"):
            return -notional * float(funding_rate)  # Shorts receive when rate is positive
        raise ValueError(f"Unsupported futures position side: {position['side']}")

    def should_apply_funding(self, position: dict, current_time_ms: int) -> bool:
        """Check if funding should be applied based on position open time and interval."""
        # Funding is applied at fixed intervals, but we simplify to check every update
        # Real implementation would track last funding time per position
        return True

    def get_funding_times(self, start_time_ms: int, end_time_ms: int) -> list[int]:
        """Get all funding timestamps between start and end (every 8 hours)."""
        import math
        # Round to nearest 8-hour boundary (00:00, 08:00, 16:00 UTC)
        interval_ms = self.FUNDING_INTERVAL_HOURS * 3600 * 1000
        first = math.ceil(start_time_ms / interval_ms) * interval_ms
        times = []
        t = first
        while t <= end_time_ms:
            times.append(t)
            t += interval_ms
        return times