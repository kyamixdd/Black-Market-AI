"""Risk management for paper trading."""
from __future__ import annotations

import math


class RiskManager:
    def __init__(self, max_risk_pct: float, max_daily_loss_pct: float,
                 max_open_risk_pct: float, max_leverage: float,
                 max_spot_positions: int, max_futures_positions: int,
                 max_position_size_pct: float = 20.0,
                 max_asset_exposure_pct: float = 30.0):
        self.max_risk_pct = max_risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_open_risk_pct = max_open_risk_pct
        self.max_leverage = max_leverage
        self.max_spot_positions = max_spot_positions
        self.max_futures_positions = max_futures_positions
        self.max_position_size_pct = float(max_position_size_pct)
        self.max_asset_exposure_pct = float(max_asset_exposure_pct)

    def check_daily_loss(self, daily_pnl: float, equity_baseline: float) -> bool:
        """Reject when total account equity drawdown reaches the daily limit."""
        try:
            pnl = float(daily_pnl)
            baseline = float(equity_baseline)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(pnl) or not math.isfinite(baseline) or baseline <= 0:
            return False
        daily_loss = max(0.0, -pnl)
        loss_pct = daily_loss / baseline * 100.0
        return loss_pct < self.max_daily_loss_pct

    def check_position_limit(self, positions: dict, max_positions: int) -> bool:
        """Check if max positions limit is reached."""
        open_count = sum(1 for p in positions.values() if p.get("status", "OPEN") in ("OPEN", "CLOSING"))
        return open_count < max_positions

    def check_symbol_exposure(self, positions: dict, symbol: str, max_per_symbol: int = 1) -> bool:
        """Check if we already have a position in this symbol."""
        count = sum(1 for p in positions.values()
                    if p.get("symbol") == symbol and p.get("status", "OPEN") in ("OPEN", "CLOSING"))
        return count < max_per_symbol

    def check_total_risk(self, current_risk: float, new_risk: float, total_balance: float) -> bool:
        """Check if total risk stays within limits."""
        try:
            values = (float(current_risk), float(new_risk), float(total_balance))
        except (TypeError, ValueError, OverflowError):
            return False
        current, added, equity = values
        if not all(math.isfinite(value) for value in values) or current < 0 or added < 0 or equity <= 0:
            return False
        return (current + added) / equity * 100 <= self.max_open_risk_pct

    def calculate_position_size(self, balance: float, risk_amount: float, max_risk_pct: float | None = None) -> float:
        """Calculate position size based on stop distance and risk budget."""
        if not math.isfinite(balance) or not math.isfinite(risk_amount) or risk_amount <= 0 or balance <= 0:
            return 0.0
        if max_risk_pct is None:
            max_risk_pct = self.max_risk_pct
        return balance * (max_risk_pct / 100.0) / risk_amount

    def validate_leverage(self, market: str, leverage: float) -> float:
        """Validate and cap leverage."""
        try:
            value = float(leverage)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if not math.isfinite(value) or value < 1.0:
            return 0.0
        if market == "FUTURES" and value > self.max_leverage:
            return self.max_leverage
        return value

    def check_position_notional(self, notional: float, equity: float) -> bool:
        try:
            amount, total = float(notional), float(equity)
        except (TypeError, ValueError, OverflowError):
            return False
        return (math.isfinite(amount) and math.isfinite(total) and amount > 0 and total > 0
                and amount / total * 100 <= self.max_position_size_pct)

    @staticmethod
    def _asset_key(symbol: str) -> str:
        value = str(symbol).upper()
        for quote in ("USDT", "USDC", "BUSD", "FDUSD", "USD", "BTC", "ETH"):
            if value.endswith(quote) and len(value) > len(quote):
                return value[:-len(quote)]
        return value

    def check_asset_exposure(self, positions: dict, symbol: str, new_notional: float,
                             equity: float, other_positions: dict | None = None) -> bool:
        try:
            added, total = float(new_notional), float(equity)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(added) or not math.isfinite(total) or added <= 0 or total <= 0:
            return False
        key = self._asset_key(symbol)
        exposure = 0.0
        for group in (positions, other_positions or {}):
            for position in group.values():
                if position.get("status", "OPEN") not in ("OPEN", "CLOSING"):
                    continue
                if self._asset_key(position.get("symbol", "")) != key:
                    continue
                try:
                    exposure += abs(float(position.get("entry_price", 0.0)) * float(position.get("amount", 0.0)))
                except (TypeError, ValueError, OverflowError):
                    return False
        return math.isfinite(exposure) and (exposure + added) / total * 100 <= self.max_asset_exposure_pct
