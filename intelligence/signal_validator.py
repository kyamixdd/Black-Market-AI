"""Signal validation rules."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from config import SIGNAL_STALE_SECONDS
from typing import Any


class SignalValidator:
    def validate(self, signal: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(signal, dict):
            return False, "Signal must be an object"

        required = ["signal_id", "symbol", "market", "strategy", "direction",
                    "timeframe", "entry", "stop_loss", "take_profit"]
        for field in required:
            if field not in signal:
                return False, f"Missing field: {field}"

        for field in ("signal_id", "symbol", "strategy", "timeframe"):
            value = signal.get(field)
            if not isinstance(value, str) or not value.strip():
                return False, f"Invalid {field}"

        from config import TIMEFRAMES
        if signal["timeframe"] not in TIMEFRAMES:
            return False, "Unsupported timeframe"

        raw_score = signal.get("raw_score", 50.0)
        if (
            isinstance(raw_score, bool)
            or not isinstance(raw_score, (int, float))
            or not math.isfinite(raw_score)
            or not 0 <= raw_score <= 100
        ):
            return False, "Invalid raw confidence score"

        created_at = signal.get("created_at")
        if created_at is not None:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except ValueError:
                    return False, "Invalid signal timestamp"
            if not isinstance(created_at, datetime):
                return False, "Invalid signal timestamp"
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
            if age_seconds < -5:
                return False, "Signal timestamp is in the future"
            if age_seconds > SIGNAL_STALE_SECONDS:
                return False, "Signal is stale"

        direction = signal.get("direction")
        if direction not in ("LONG", "BUY", "SHORT", "SELL"):
            return False, "Unsupported direction"

        market = signal.get("market")
        if market not in ("SPOT", "FUTURES"):
            return False, "Unsupported market"
        if market == "SPOT" and direction in ("SHORT", "SELL"):
            return False, "Spot market does not support short positions"

        entry = signal.get("entry")
        stop_loss = signal.get("stop_loss")
        take_profits = signal.get("take_profit")
        if (
            isinstance(entry, bool)
            or isinstance(stop_loss, bool)
            or not isinstance(entry, (int, float))
            or not isinstance(stop_loss, (int, float))
            or not math.isfinite(entry)
            or not math.isfinite(stop_loss)
            or entry <= 0
            or stop_loss <= 0
            or not isinstance(take_profits, (list, tuple))
            or not take_profits
        ):
            return False, "Invalid price levels"

        if any(
            isinstance(target, bool)
            or not isinstance(target, (int, float))
            or not math.isfinite(target)
            or target <= 0
            for target in take_profits
        ):
            return False, "Invalid take-profit levels"

        is_long = direction in ("LONG", "BUY")
        if is_long and not (stop_loss < entry < min(take_profits)):
            return False, "Invalid LONG/BUY price order"
        if not is_long and not (max(take_profits) < entry < stop_loss):
            return False, "Invalid SHORT/SELL price order"

        risk = abs(entry - stop_loss)
        reward = abs(take_profits[0] - entry)
        if risk <= 0 or reward / risk < 0.5:
            return False, "Poor risk-reward"
        return True, "OK"
