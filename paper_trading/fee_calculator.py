"""Trading fee, slippage, and spread calculations for Spot and Futures."""
from __future__ import annotations

SPOT_MAKER = 0.001
SPOT_TAKER = 0.001
FUTURES_MAKER = 0.0002
FUTURES_TAKER = 0.0005

# Spread assumptions (basis points)
SPOT_SPREAD_BPS = 2  # 0.02%
FUTURES_SPREAD_BPS = 1  # 0.01%

# Slippage assumptions (basis points) - additional cost beyond spread
SPOT_SLIPPAGE_BPS = 5  # 0.05% for market orders
FUTURES_SLIPPAGE_BPS = 3  # 0.03% for market orders
LIMIT_ORDER_SLIPPAGE_BPS = 0  # No slippage for limit orders (if filled)


class FeeCalculator:
    def calculate(self, market: str, direction: str, amount: float, price: float,
                  leverage: float = 1.0) -> float:
        """Calculate trading fee for a position."""
        notional = amount * price
        if market == "SPOT":
            return notional * SPOT_TAKER
        return notional * FUTURES_TAKER

    def calculate_slippage(self, market: str, order_type: str, amount: float, price: float,
                           leverage: float = 1.0, volume_24h: float = 0.0) -> float:
        """Calculate slippage in price terms.

        Returns the slippage-adjusted price impact (positive for buys, negative for sells).
        """
        notional = amount * price

        if order_type == "LIMIT":
            return 0.0

        # Base slippage in basis points
        if market == "SPOT":
            base_slippage_bps = SPOT_SLIPPAGE_BPS
        else:
            base_slippage_bps = FUTURES_SLIPPAGE_BPS

        # Volume impact adjustment - larger orders on low-volume symbols get more slippage
        volume_impact = 0.0
        if volume_24h > 0:
            volume_ratio = notional / volume_24h
            # Scale impact: 0.1% volume -> 1x, 1% volume -> 3x, 5% volume -> 10x
            if volume_ratio > 0.001:
                volume_impact = min(volume_ratio * 100, 10.0)

        total_slippage_bps = base_slippage_bps * (1 + volume_impact)

        # Convert to price adjustment
        slippage_pct = total_slippage_bps / 10000.0
        return price * slippage_pct

    def calculate_spread(self, market: str, price: float) -> float:
        """Calculate half-spread (cost to cross the spread)."""
        if market == "SPOT":
            spread_bps = SPOT_SPREAD_BPS
        else:
            spread_bps = FUTURES_SPREAD_BPS
        return price * (spread_bps / 10000.0)

    def get_fill_price(self, market: str, direction: str, order_type: str, price: float,
                       amount: float, leverage: float = 1.0, volume_24h: float = 0.0) -> float:
        """Get the realistic fill price including spread and slippage."""
        if order_type == "LIMIT":
            # A limit order cannot execute at a price worse than its limit.
            return price
        spread = self.calculate_spread(market, price)
        slippage = self.calculate_slippage(market, order_type, amount, price, leverage, volume_24h)

        # Both spread and slippage work against the trader
        if direction in ("BUY", "LONG"):
            return price + spread + slippage
        else:
            return price - spread - slippage