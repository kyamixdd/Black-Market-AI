"""Signal validation rules."""
from __future__ import annotations

from typing import Any


class SignalValidator:
    def validate(self, signal: dict[str, Any]) -> tuple[bool, str]:
        # Basic field presence
        required = ["signal_id", "symbol", "market", "strategy", "direction",
                    "timeframe", "entry", "stop_loss", "take_profit"]
        for f in required:
            if f not in signal:
                return False, f"Missing field: {f}"
        # Price logic
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tps = signal.get("take_profit", [])
        if not tps or entry <= 0 or sl <= 0:
            return False, "Invalid price levels"
        direction = signal.get("direction", "")
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