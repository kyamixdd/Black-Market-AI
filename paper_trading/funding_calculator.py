"""Futures funding payment calculation."""
from __future__ import annotations

import math
from datetime import datetime, timezone


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
        try:
            rate = float(funding_rate)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Funding rate must be finite.")
        if not math.isfinite(rate):
            raise ValueError("Funding rate must be finite.")
        # Funding is charged on the position's current notional value, not
        # the initial margin. Leverage changes required margin, not the
        # quantity of underlying exposure being funded.
        funding_price = mark_price if mark_price is not None else (position.get("current_price") or position["entry_price"])
        funding_price = float(funding_price)
        if not math.isfinite(funding_price) or funding_price <= 0:
            raise ValueError("Funding mark price must be finite and positive.")
        notional = float(position["amount"]) * funding_price
        if position["side"] in ("LONG", "BUY"):
            return notional * rate
        if position["side"] in ("SHORT", "SELL"):
            return -notional * rate  # Shorts receive when rate is positive
        raise ValueError(f"Unsupported futures position side: {position['side']}")

    def should_apply_funding(self, position: dict, current_time_ms: int) -> bool:
        """Return whether a UTC 8-hour settlement boundary is newly eligible."""
        if position.get("market") != "FUTURES":
            return False
        interval_ms = self.FUNDING_INTERVAL_HOURS * 3600 * 1000
        boundary = (int(current_time_ms) // interval_ms) * interval_ms
        last = int(position.get("last_funding_time", 0) or 0)
        opened_at = position.get("opened_at")
        if isinstance(opened_at, datetime):
            opened_at = (opened_at.replace(tzinfo=timezone.utc) if opened_at.tzinfo is None else opened_at)
            opened_ms = int(opened_at.timestamp() * 1000)
        else:
            opened_ms = 0
        return boundary > max(last, opened_ms)

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