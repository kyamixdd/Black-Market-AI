"""Paper trading simulator: virtual accounts, orders, positions, P&L."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from config import (
    FUTURES_INITIAL_BALANCE,
    MAX_FUTURES_POSITIONS,
    MAX_SPOT_POSITIONS,
    RISK_MAX_DAILY_LOSS_PCT,
    RISK_MAX_LEVERAGE,
    RISK_MAX_TOTAL_OPEN_PCT,
    RISK_PER_TRADE_PCT,
    SPOT_INITIAL_BALANCE,
)
from core.event_bus import EventBus
from core.event_models import EventType, make_event
from paper_trading.fee_calculator import FeeCalculator
from paper_trading.funding_calculator import FundingCalculator
from paper_trading.liquidation_engine import LiquidationEngine
from paper_trading.pnl_calculator import PnLCalculator
from paper_trading.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class Simulator:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.initial_spot_balance = SPOT_INITIAL_BALANCE
        self.initial_futures_balance = FUTURES_INITIAL_BALANCE
        self.spot_balance = self.initial_spot_balance
        self.futures_balance = self.initial_futures_balance
        self.spot_positions: dict[str, dict] = {}
        self.futures_positions: dict[str, dict] = {}
        self.open_orders: dict[str, dict] = {}
        self.closed_trades: list[dict] = []
        self.daily_pnl = 0.0
        self.daily_pnl_date = datetime.now(timezone.utc).date()
        self.fee_calc = FeeCalculator()
        self.funding_calc = FundingCalculator()
        self.liquidation = LiquidationEngine()
        self.pnl_calc = PnLCalculator()
        self.risk_manager = RiskManager(
            max_risk_pct=RISK_PER_TRADE_PCT,
            max_daily_loss_pct=RISK_MAX_DAILY_LOSS_PCT,
            max_open_risk_pct=RISK_MAX_TOTAL_OPEN_PCT,
            max_leverage=RISK_MAX_LEVERAGE,
            max_spot_positions=MAX_SPOT_POSITIONS,
            max_futures_positions=MAX_FUTURES_POSITIONS,
        )

    def get_balance(self, market: str) -> float:
        return self.spot_balance if market == "SPOT" else self.futures_balance

    def get_daily_pnl(self) -> float:
        """Return realized P&L for the current UTC calendar day."""
        today = datetime.now(timezone.utc).date()
        if self.daily_pnl_date != today:
            self.daily_pnl = 0.0
            self.daily_pnl_date = today
        return self.daily_pnl

    def _get_positions(self, market: str) -> dict[str, dict]:
        return self.spot_positions if market == "SPOT" else self.futures_positions

    def _get_total_risk(self) -> float:
        total = 0.0
        for pos in self.spot_positions.values():
            if pos.get("stop_loss"):
                risk = abs(pos["entry_price"] - pos["stop_loss"]) * pos["amount"]
                total += risk
        for pos in self.futures_positions.values():
            if pos.get("stop_loss"):
                risk = abs(pos["entry_price"] - pos["stop_loss"]) * pos["amount"]
                total += risk
        return total

    def _get_volume_24h(self, market: str, symbol: str) -> float:
        """Get 24h volume for slippage calculation - placeholder, will be wired to market cache."""
        # This should be replaced with actual market cache data
        return 1000000.0  # Default 1M USDT volume

    def validate_new_position(self, signal: dict[str, Any]) -> tuple[bool, str]:
        market = signal["market"]
        direction = signal["direction"]
        positions = self._get_positions(market)

        # Check total position limit using risk manager
        max_positions = MAX_SPOT_POSITIONS if market == "SPOT" else MAX_FUTURES_POSITIONS
        if not self.risk_manager.check_position_limit(positions, max_positions):
            return False, f"Max {market} positions reached"

        # Check per-symbol position limit
        if not self.risk_manager.check_symbol_exposure(positions, signal["symbol"]):
            return False, f"Position already open for {signal['symbol']} on {market}"

        # Risk manager - daily loss check
        total_balance = self.spot_balance + self.futures_balance
        if not self.risk_manager.check_daily_loss(self.get_daily_pnl(), total_balance):
            return False, "Daily loss limit exceeded"

        # Risk manager check
        balance = self.get_balance(market)
        risk_amount = abs(signal["entry"] - signal["stop_loss"])
        if risk_amount <= 0:
            return False, "Invalid stop loss"
        qty = self.risk_manager.calculate_position_size(balance, risk_amount)
        if qty <= 0:
            return False, "Calculated quantity is zero"
        # Leverage
        leverage = signal.get("leverage", 1.0)
        leverage = self.risk_manager.validate_leverage(market, leverage)
        # Total open risk
        total_risk = self._get_total_risk()
        new_risk = risk_amount * qty
        if not self.risk_manager.check_total_risk(total_risk, new_risk, total_balance):
            return False, "Total open risk limit exceeded"
        return True, "OK"

    async def execute_signal(self, signal: dict[str, Any]) -> str | None:
        """Execute a validated signal into a paper position."""
        ok, reason = self.validate_new_position(signal)
        if not ok:
            logger.warning("Signal %s risk check failed: %s", signal["signal_id"], reason)
            return None
        market = signal["market"]
        balance = self.get_balance(market)
        risk_amount = abs(signal["entry"] - signal["stop_loss"])
        qty = balance * (RISK_PER_TRADE_PCT / 100.0) / risk_amount
        leverage = signal.get("leverage", 1.0)
        if market == "FUTURES" and leverage > RISK_MAX_LEVERAGE:
            leverage = RISK_MAX_LEVERAGE

        # Get realistic fill price with spread and slippage
        volume_24h = self._get_volume_24h(market, signal["symbol"])
        order_type = signal.get("order_type", "MARKET")
        fill_price = self.fee_calc.get_fill_price(
            market, signal["direction"], order_type, signal["entry"],
            qty, leverage, volume_24h
        )

        # Deduct fees upfront
        fee = self.fee_calc.calculate(market, signal["direction"], qty, fill_price, leverage)
        position_id = f"POS-{uuid.uuid4().hex[:8].upper()}"
        position = {
            "position_id": position_id,
            "symbol": signal["symbol"],
            "market": market,
            "side": signal["direction"],
            "entry_price": fill_price,
            "amount": qty,
            "current_price": fill_price,
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"][0] if signal["take_profit"] else None,
            "leverage": leverage,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "fees_paid": fee,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
            "order_type": order_type,
            "signal_id": signal.get("signal_id"),
            "strategy": signal.get("strategy", "UNKNOWN"),
        }
        if market == "SPOT":
            self.spot_positions[position_id] = position
            self.spot_balance -= fee
        else:
            self.futures_positions[position_id] = position
            self.futures_balance -= fee
        await self.event_bus.publish(make_event(
            EventType.POSITION_OPENED, "simulator",
            symbol=signal["symbol"], market=market, position=position
        ))
        logger.info("Opened %s position %s %s @ %.4f (fill: %.4f)", market, signal["direction"], signal["symbol"], signal["entry"], fill_price)
        return position_id

    async def update_prices(self, market: str, symbol: str, price: float,
                        mark_price: float | None = None, funding_rate: float | None = None) -> None:
        positions = self._get_positions(market)
        # Iterate over a copy to avoid "dictionary changed size during iteration"
        for pos in list(positions.values()):
            if pos["symbol"] == symbol and pos["status"] == "OPEN":
                pos["current_price"] = price
                pos["unrealized_pnl"] = self.pnl_calc.unrealized(pos, price)

                # Check liquidation first for futures
                if market == "FUTURES" and pos["status"] == "OPEN":
                    await self._check_liquidation(pos, mark_price or price)

                # Check stop/tp if still open
                if pos["status"] == "OPEN":
                    await self._check_exit(pos, price, market)

                # Apply funding if rate provided
                if market == "FUTURES" and pos["status"] == "OPEN" and funding_rate is not None:
                    await self._apply_funding(pos, funding_rate)

    async def _check_exit(self, position: dict, price: float, market: str) -> None:
        side = position["side"]
        sl = position.get("stop_loss")
        tp = position.get("take_profit")
        hit = False
        reason = ""
        if side in ("LONG", "BUY"):
            if sl and price <= sl:
                hit, reason = True, "STOP_LOSS"
            elif tp and price >= tp:
                hit, reason = True, "TAKE_PROFIT"
        elif side in ("SHORT", "SELL"):
            if sl and price >= sl:
                hit, reason = True, "STOP_LOSS"
            elif tp and price <= tp:
                hit, reason = True, "TAKE_PROFIT"
        if hit:
            await self._close_position(position, price, reason)

    async def _check_liquidation(self, position: dict, mark_price: float) -> None:
        """Check and execute liquidation for futures positions."""
        # Check if position is at risk (close to liquidation)
        if self.liquidation.is_at_risk(position, mark_price):
            margin_ratio = self.liquidation.get_margin_ratio(position, mark_price)
            logger.warning("Margin call risk for %s %s: margin_ratio=%.4f, mark=%.4f",
                          position["symbol"], position["side"], margin_ratio, mark_price)
            await self.event_bus.publish(make_event(
                EventType.RISK_ALERT, "simulator",
                symbol=position["symbol"], market=position["market"],
                payload={
                    "alert_type": "MARGIN_RISK",
                    "message": f"Position {position['symbol']} near liquidation",
                    "margin_ratio": margin_ratio,
                    "mark_price": mark_price,
                    "liquidation_price": self.liquidation.calculate_liquidation_price(position),
                }
            ))

        if self.liquidation.check_liquidation(position, mark_price):
            liq_price = self.liquidation.calculate_liquidation_price(position)
            logger.warning("LIQUIDATION triggered for %s %s @ %.4f (liq: %.4f)",
                          position["symbol"], position["side"], mark_price, liq_price)
            await self._close_position(position, mark_price, "LIQUIDATION")
            await self.event_bus.publish(make_event(
                EventType.RISK_ALERT, "simulator",
                symbol=position["symbol"], market=position["market"],
                payload={
                    "alert_type": "LIQUIDATION",
                    "message": f"Position {position['symbol']} liquidated",
                    "liquidation_price": liq_price,
                    "mark_price": mark_price,
                }
            ))

    async def _apply_funding(self, position: dict, funding_rate: float) -> None:
        """Apply funding payment to futures position."""
        # Track last funding time to avoid double-paying
        current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        last_funding = position.get("last_funding_time", 0)

        # Only apply if enough time has passed (8 hours)
        if current_time_ms - last_funding < 8 * 3600 * 1000:
            return

        payment = self.funding_calc.calculate(position, funding_rate)
        position["fees_paid"] += payment
        position["last_funding_time"] = current_time_ms
        if position["market"] == "FUTURES":
            self.futures_balance -= payment
        logger.debug("Funding payment for %s: %.4f (rate: %.6f)", position["symbol"], payment, funding_rate)

    async def _close_position(self, position: dict, exit_price: float, reason: str) -> None:
        market = position["market"]
        # Get realistic fill price with spread and slippage on exit
        volume_24h = self._get_volume_24h(market, position["symbol"])
        order_type = position.get("order_type", "MARKET")
        fill_price = self.fee_calc.get_fill_price(
            market, position["side"], order_type, exit_price,
            position["amount"], position["leverage"], volume_24h
        )

        pnl = self.pnl_calc.realized(position, fill_price)
        fee = self.fee_calc.calculate(market, position["side"], position["amount"], fill_price, position["leverage"])
        balance_delta = pnl - fee
        trade_pnl = pnl - position.get("fees_paid", 0.0) - fee
        position["status"] = "CLOSED"
        position["closed_at"] = datetime.now(timezone.utc)
        position["close_price"] = fill_price
        position["realized_pnl"] = trade_pnl
        position["fees_paid"] += fee
        if market == "SPOT":
            self.spot_balance += balance_delta
            pos_dict = self.spot_positions
        else:
            self.futures_balance += balance_delta
            pos_dict = self.futures_positions
        # Record trade
        trade = {
            "position_id": position["position_id"],
            "symbol": position["symbol"],
            "market": market,
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": fill_price,
            "amount": position["amount"],
            "leverage": position["leverage"],
            "pnl": trade_pnl,
            "pnl_pct": (trade_pnl / (position["entry_price"] * position["amount"])) * 100,
            "fee": position["fees_paid"],
            "strategy": position.get("strategy", "UNKNOWN"),
            "signal_id": position.get("signal_id"),
            "opened_at": position["opened_at"],
            "closed_at": datetime.now(timezone.utc),
            "close_reason": reason,
        }
        self.closed_trades.append(trade)
        self.get_daily_pnl()
        self.daily_pnl += trade_pnl
        del pos_dict[position["position_id"]]
        await self.event_bus.publish(make_event(
            EventType.POSITION_CLOSED, "simulator",
            symbol=position["symbol"], market=market, trade=trade
        ))
        logger.info("Closed %s %s PnL: %.2f (%s, fill: %.4f)", position["symbol"], position["side"], trade_pnl, reason, fill_price)

    # --- Limit Order Handling ---
    async def place_limit_order(self, signal: dict[str, Any]) -> str | None:
        """Place a simulated limit order."""
        ok, reason = self.validate_new_position(signal)
        if not ok:
            logger.warning("Limit order %s risk check failed: %s", signal["signal_id"], reason)
            return None

        market = signal["market"]
        balance = self.get_balance(market)
        risk_amount = abs(signal["entry"] - signal["stop_loss"])
        qty = balance * (RISK_PER_TRADE_PCT / 100.0) / risk_amount
        leverage = signal.get("leverage", 1.0)
        if market == "FUTURES" and leverage > RISK_MAX_LEVERAGE:
            leverage = RISK_MAX_LEVERAGE

        # Limit orders don't fill immediately - they go to open_orders
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order = {
            "order_id": order_id,
            "symbol": signal["symbol"],
            "market": market,
            "side": signal["direction"],
            "entry_price": signal["entry"],
            "amount": qty,
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"][0] if signal["take_profit"] else None,
            "leverage": leverage,
            "order_type": "LIMIT",
            "status": "OPEN",
            "created_at": datetime.now(timezone.utc),
            "signal_id": signal.get("signal_id"),
            "strategy": signal.get("strategy", "UNKNOWN"),
        }
        self.open_orders[order_id] = order
        await self.event_bus.publish(make_event(
            EventType.ORDER_PLACED, "simulator",
            symbol=signal["symbol"], market=market, order=order
        ))
        logger.info("Placed LIMIT order %s %s %s @ %.4f", market, signal["direction"], signal["symbol"], signal["entry"])
        return order_id

    async def check_limit_orders(self, market: str, symbol: str, price: float) -> None:
        """Check if any limit orders should be filled at current price."""
        for order in list(self.open_orders.values()):
            if order["market"] != market or order["symbol"] != symbol or order["status"] != "OPEN":
                continue
            side = order["side"]
            limit_price = order["entry_price"]
            hit = False
            if side in ("LONG", "BUY") and price <= limit_price or side in ("SHORT", "SELL") and price >= limit_price:
                hit = True
            if hit:
                # Convert limit order to position
                order["status"] = "FILLED"
                signal = {
                    "signal_id": order.get("signal_id", "LIMIT-" + order["order_id"]),
                    "symbol": order["symbol"],
                    "market": order["market"],
                    "direction": order["side"],
                    "entry": order["entry_price"],
                    "stop_loss": order["stop_loss"],
                    "take_profit": [order["take_profit"]] if order["take_profit"] else [],
                    "leverage": order["leverage"],
                    "order_type": "LIMIT",
                    "strategy": order.get("strategy", "UNKNOWN"),
                }
                await self.execute_signal(signal)
                del self.open_orders[order["order_id"]]
                await self.event_bus.publish(make_event(
                    EventType.ORDER_FILLED, "simulator",
                    symbol=order["symbol"], market=order["market"], order=order
                ))

    # --- Restart Recovery ---
    def get_state_snapshot(self) -> dict[str, Any]:
        """Get complete state for persistence/recovery."""
        return {
            "spot_balance": self.spot_balance,
            "futures_balance": self.futures_balance,
            "spot_positions": self.spot_positions,
            "futures_positions": self.futures_positions,
            "open_orders": self.open_orders,
            "closed_trades": self.closed_trades,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_date": self.daily_pnl_date.isoformat(),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore state from persistence."""
        self.spot_balance = state.get("spot_balance", SPOT_INITIAL_BALANCE)
        self.futures_balance = state.get("futures_balance", FUTURES_INITIAL_BALANCE)
        self.spot_positions = state.get("spot_positions", {})
        self.futures_positions = state.get("futures_positions", {})
        self.open_orders = state.get("open_orders", {})
        self.closed_trades = state.get("closed_trades", [])
        daily_pnl_date = state.get("daily_pnl_date")
        try:
            self.daily_pnl_date = datetime.fromisoformat(daily_pnl_date).date() if daily_pnl_date else datetime.now(timezone.utc).date()
        except (TypeError, ValueError):
            self.daily_pnl_date = datetime.now(timezone.utc).date()
        self.daily_pnl = state.get("daily_pnl", 0.0)
        self.get_daily_pnl()
        logger.info("Restored state: Spot=%.2f, Futures=%.2f, OpenPos=%d, Trades=%d",
                    self.spot_balance, self.futures_balance,
                    len(self.spot_positions) + len(self.futures_positions),
                    len(self.closed_trades))