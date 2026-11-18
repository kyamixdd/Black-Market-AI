"""Liquidation simulation for futures positions."""
from __future__ import annotations


class LiquidationEngine:
    # Binance maintenance margin rates (varies by position size, simplified)
    DEFAULT_MMR = 0.05  # 5% for small positions

    def calculate_liquidation_price(self, position: dict) -> float:
        """Calculate the liquidation price for a position."""
        if position["market"] != "FUTURES":
            return 0.0

        leverage = position.get("leverage", 1.0)
        mmr = self.DEFAULT_MMR

        if position["side"] in ("LONG", "BUY"):
            # Long liquidation: mark_price <= entry * (1 - 1/leverage + mmr)
            return position["entry_price"] * (1 - (1 / leverage) + mmr)
        else:
            # Short liquidation: mark_price >= entry * (1 + 1/leverage - mmr)
            return position["entry_price"] * (1 + (1 / leverage) - mmr)

    def check_liquidation(self, position: dict, mark_price: float) -> bool:
        """Check if position should be liquidated at current mark price."""
        if position["market"] != "FUTURES":
            return False

        liq_price = self.calculate_liquidation_price(position)
        if position["side"] in ("LONG", "BUY"):
            return mark_price <= liq_price
        else:
            return mark_price >= liq_price

    def get_margin_ratio(self, position: dict, mark_price: float) -> float:
        """Calculate current margin ratio (maintenance margin / position value)."""
        if position["market"] != "FUTURES":
            return 1.0

        leverage = position.get("leverage", 1.0)
        entry_price = position["entry_price"]

        if position["side"] in ("LONG", "BUY"):
            pnl_pct = (mark_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - mark_price) / entry_price

        # Margin ratio = (1 + pnl_pct) * leverage
        # If this drops below MMR, liquidation triggers
        return (1 + pnl_pct) * leverage

    def is_at_risk(self, position: dict, mark_price: float, threshold: float = 1.2) -> bool:
        """Check if position is close to liquidation (margin ratio < threshold * MMR)."""
        margin_ratio = self.get_margin_ratio(position, mark_price)
        return margin_ratio < (threshold * self.DEFAULT_MMR)