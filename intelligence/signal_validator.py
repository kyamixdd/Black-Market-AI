"""Signal validation rules."""
from __future__ import annotations

import math
from typing import Any

_VALID_DIRECTIONS = {"LONG", "BUY", "SHORT", "SELL"}


class SignalValidator:
    def validate(self, signal: dict[str, Any]) -> tuple[bool, str]:
        # Basic field presence
        required = ["signal_id", "symbol", "market", "strategy", "direction",
                    "timeframe", "entry", "stop_loss", "take_profit"]
        for f in required:
            if f not in signal:
                return False, f"Missing field: {f}"
        # Price sanity — must be finite positive numbers (I-3)
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tps = signal.get("take_profit", [])
        if not math.isfinite(entry) or not math.isfinite(sl):
            return False, "Non-finite price value"
        if not tps or entry <= 0 or sl <= 0:
            return False, "Invalid price levels"
        if not all(math.isfinite(t) and t > 0 for t in tps):
            return False, "Invalid take-profit values"
        # Direction must be one of the known set (I-3)
        direction = signal.get("direction", "")
        if direction not in _VALID_DIRECTIONS:
            return False, f"Unknown direction: {direction!r}"
        if direction in ("LONG", "BUY"):
            if not (sl < entry < min(tps)):
                return False, "Invalid LONG/BUY price order"
        elif direction in ("SHORT", "SELL"):
            if not (max(tps) < entry < sl):
                return False, "Invalid SHORT/SELL price order"
        # Risk check
        risk = abs(entry - sl)
        reward = abs(tps[0] - entry)
        if risk <= 0 or reward / risk < 0.5:
            return False, "Poor risk-reward"
        return True, "OK"