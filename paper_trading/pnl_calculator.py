"""P&L calculation for paper positions."""
from __future__ import annotations


class PnLCalculator:
    def unrealized(self, position: dict, current_price: float) -> float:
        if position["side"] in ("LONG", "BUY"):
            return (current_price - position["entry_price"]) * position["amount"] * position.get("leverage", 1.0)
        else:
            return (position["entry_price"] - current_price) * position["amount"] * position.get("leverage", 1.0)

    def realized(self, position: dict, exit_price: float) -> float:
        if position["side"] in ("LONG", "BUY"):
            return (exit_price - position["entry_price"]) * position["amount"] * position.get("leverage", 1.0)
        else:
            return (position["entry_price"] - exit_price) * position["amount"] * position.get("leverage", 1.0)