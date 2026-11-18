"""Risk management for paper trading."""
from __future__ import annotations


class RiskManager:
    def __init__(self, max_risk_pct: float, max_daily_loss_pct: float,
                 max_open_risk_pct: float, max_leverage: float,
                 max_spot_positions: int, max_futures_positions: int):
        self.max_risk_pct = max_risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_open_risk_pct = max_open_risk_pct
        self.max_leverage = max_leverage
        self.max_spot_positions = max_spot_positions
        self.max_futures_positions = max_futures_positions

    def check_daily_loss(self, daily_pnl: float, total_balance: float) -> bool:
        """Allow entries unless realized losses reach the configured daily cap.

        Profits must not consume the loss allowance; only the negative portion
        of daily P&L represents daily loss.
        """
        if total_balance <= 0:
            return False
        daily_loss = max(0.0, -daily_pnl)
        return daily_loss / total_balance * 100 < self.max_daily_loss_pct

    def check_position_limit(self, positions: dict, max_positions: int) -> bool:
        """Check if max positions limit is reached."""
        open_count = sum(1 for p in positions.values() if p.get("status") == "OPEN")
        return open_count < max_positions

    def check_symbol_exposure(self, positions: dict, symbol: str, max_per_symbol: int = 1) -> bool:
        """Check if we already have a position in this symbol."""
        count = sum(1 for p in positions.values()
                    if p.get("symbol") == symbol and p.get("status") == "OPEN")
        return count < max_per_symbol

    def check_total_risk(self, current_risk: float, new_risk: float, total_balance: float) -> bool:
        """Check if total risk stays within limits."""
        if total_balance <= 0:
            return False
        return (current_risk + new_risk) / total_balance * 100 <= self.max_open_risk_pct

    def calculate_position_size(self, balance: float, risk_amount: float, max_risk_pct: float | None = None) -> float:
        """Calculate position size based on risk per trade."""
        if max_risk_pct is None:
            max_risk_pct = self.max_risk_pct
        if balance <= 0 or risk_amount <= 0 or max_risk_pct <= 0:
            return 0.0
        return balance * (max_risk_pct / 100.0) / risk_amount

    def validate_leverage(self, market: str, leverage: float) -> float:
        """Validate and cap leverage."""
        if market == "FUTURES" and leverage > self.max_leverage:
            return self.max_leverage
        return leverage
