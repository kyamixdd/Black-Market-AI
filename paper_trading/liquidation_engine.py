"""Liquidation simulation for futures positions."""
from __future__ import annotations

import math


class LiquidationEngine:
    # Binance maintenance margin rates (varies by position size, simplified)
    DEFAULT_MMR = 0.05  # 5% for small positions

    def calculate_liquidation_price(self, position: dict) -> float:
        """Calculate the liquidation price for a position."""
        if position["market"] != "FUTURES":
            return 0.0

        try:
            entry = float(position.get("entry_price", 0.0))
            leverage = float(position.get("leverage", 0.0))
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if not math.isfinite(entry) or not math.isfinite(leverage) or entry <= 0 or leverage < 1.0:
            return 0.0
        mmr = self.DEFAULT_MMR

        if str(position.get("side", "")).upper() in ("LONG", "BUY"):
            # Long liquidation: mark_price <= entry * (1 - 1/leverage + mmr)
            return entry * (1 - (1 / leverage) + mmr)
        else:
            # Short liquidation: mark_price >= entry * (1 + 1/leverage - mmr)
            return entry * (1 + (1 / leverage) - mmr)

    def check_liquidation(self, position: dict, mark_price: float) -> bool:
        """Check if position should be liquidated at current mark price."""
        if position["market"] != "FUTURES":
            return False

        try:
            price = float(mark_price)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(price) or price <= 0:
            return False
        liq_price = self.calculate_liquidation_price(position)
        if liq_price <= 0:
            return False
        if str(position.get("side", "")).upper() in ("LONG", "BUY"):
            return price <= liq_price
        else:
            return price >= liq_price

    def get_margin_ratio(self, position: dict, mark_price: float) -> float:
        """Calculate current margin ratio (maintenance margin / position value)."""
        if position["market"] != "FUTURES":
            return 1.0

        try:
            leverage = float(position.get("leverage", 0.0))
            entry_price = float(position.get("entry_price", 0.0))
            price = float(mark_price)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if (not all(math.isfinite(value) for value in (leverage, entry_price, price))
                or leverage < 1.0 or entry_price <= 0 or price <= 0):
            return 0.0

        if str(position.get("side", "")).upper() in ("LONG", "BUY"):
            pnl_pct = (price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - price) / entry_price

        # Margin ratio = (1 + pnl_pct) * leverage
        # If this drops below MMR, liquidation triggers
        return (1 + pnl_pct) * leverage

    def is_at_risk(self, position: dict, mark_price: float, threshold: float = 1.2) -> bool:
        """Check if position is close to liquidation (margin ratio < threshold * MMR)."""
        try:
            ratio = float(self.get_margin_ratio(position, mark_price))
            limit = float(threshold) * self.DEFAULT_MMR
        except (TypeError, ValueError, OverflowError):
            return False
        return math.isfinite(ratio) and math.isfinite(limit) and ratio < limit