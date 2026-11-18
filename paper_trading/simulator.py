"""Paper trading simulator: virtual accounts, orders, positions, P&L."""
from __future__ import annotations

import logging
import math
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
from paper_trading.fee_calculator import FeeCalculator, FUTURES_TAKER, SPOT_TAKER
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
        self.market_volumes: dict[tuple[str, str], float] = {}
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

    def _get_total_equity(self) -> float:
        """Free cash plus reserved margin and current unrealized P&L."""
        spot_margin = sum(
            p.get("margin", p.get("entry_price", 0.0) * p.get("amount", 0.0))
            for p in self.spot_positions.values()
        )
        futures_margin = sum(
            p.get("margin", p.get("entry_price", 0.0) * p.get("amount", 0.0))
            for p in self.futures_positions.values()
        )
        unrealized = sum(
            p.get("unrealized_pnl", 0.0)
            for p in list(self.spot_positions.values()) + list(self.futures_positions.values())
        )
        return max(0.0, self.spot_balance + self.futures_balance + spot_margin + futures_margin + unrealized)

    def _get_total_risk(self) -> float:
        total = 0.0
        for pos in self.spot_positions.values():
            if pos.get("stop_loss"):
                risk = abs(pos["entry_price"] - pos["stop_loss"]) * pos["amount"] * pos.get("leverage", 1.0)
                total += risk
        for pos in self.futures_positions.values():
            if pos.get("stop_loss"):
                risk = abs(pos["entry_price"] - pos["stop_loss"]) * pos["amount"] * pos.get("leverage", 1.0)
                total += risk
        return total

    def update_market_volume(self, market: str, symbol: str, volume_24h: float) -> None:
        if isinstance(volume_24h, (int, float)) and volume_24h >= 0:
            self.market_volumes[(market, symbol)] = float(volume_24h)

    def _get_volume_24h(self, market: str, symbol: str) -> float:
        """Return the latest quote-volume estimate for realistic slippage."""
        return self.market_volumes.get((market, symbol), 0.0)

    def _available_balance(self, market: str, exclude_order_id: str | None = None) -> float:
        """Free balance after reserving capital for pending limit orders."""
        fee_rate = SPOT_TAKER if market == "SPOT" else FUTURES_TAKER
        reserved = 0.0
        for order_id, order in self.open_orders.items():
            if order_id == exclude_order_id or order.get("market") != market or order.get("status") != "OPEN":
                continue
            leverage = float(order.get("leverage", 1.0))
            reserved += (
                float(order.get("amount", 0.0))
                * float(order.get("entry_price", 0.0))
                * (1.0 + fee_rate * leverage)
            )
        return max(0.0, self.get_balance(market) - reserved)

    def _effective_leverage(self, signal: dict[str, Any]) -> float:
        market = signal.get("market")
        requested = signal.get("leverage", 1.0)
        if isinstance(requested, bool) or not isinstance(requested, (int, float)):
            return 0.0
        if not isinstance(requested, (int, float)) or not math.isfinite(requested) or requested < 1:
            return 0.0
        if market == "SPOT":
            return 1.0
        return self.risk_manager.validate_leverage(market, float(requested))

    def _calculate_quantity(
        self, balance: float, risk_distance: float, leverage: float,
        entry_price: float, market: str,
    ) -> float:
        if balance <= 0 or risk_distance <= 0 or leverage <= 0 or entry_price <= 0:
            return 0.0
        risk_quantity = balance * (RISK_PER_TRADE_PCT / 100.0) / (risk_distance * leverage)
        fee_rate = SPOT_TAKER if market == "SPOT" else FUTURES_TAKER
        capital_per_unit = entry_price * (1.0 + fee_rate * leverage)
        capital_quantity = balance / capital_per_unit
        return min(risk_quantity, capital_quantity)

    def validate_new_position(self, signal: dict[str, Any]) -> tuple[bool, str]:
        market = signal.get("market")
        direction = signal.get("direction")
        if market not in ("SPOT", "FUTURES"):
            return False, "Unsupported market"
        if direction not in ("LONG", "BUY", "SHORT", "SELL"):
            return False, "Unsupported direction"
        if market == "SPOT" and direction in ("SHORT", "SELL"):
            return False, "Spot market does not support short positions"
        symbol = signal.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            return False, "Invalid symbol"
        entry = signal.get("entry")
        stop_loss = signal.get("stop_loss")
        if (
            isinstance(entry, bool) or isinstance(stop_loss, bool)
            or not isinstance(entry, (int, float)) or not isinstance(stop_loss, (int, float))
            or not math.isfinite(entry) or not math.isfinite(stop_loss)
            or entry <= 0 or stop_loss <= 0
        ):
            return False, "Invalid entry or stop-loss price"
        risk_amount = abs(float(entry) - float(stop_loss))
        if risk_amount <= 0:
            return False, "Invalid stop loss"
        take_profits = signal.get("take_profit")
        if not isinstance(take_profits, (list, tuple)) or not take_profits:
            return False, "At least one take-profit target is required"
        if any(
            isinstance(target, bool) or not isinstance(target, (int, float))
            or not math.isfinite(target) or target <= 0
            for target in take_profits
        ):
            return False, "Invalid take-profit target"
        is_long = direction in ("LONG", "BUY")
        if is_long and not (stop_loss < entry < min(take_profits)):
            return False, "Invalid LONG/BUY stop-loss or take-profit ordering"
        if not is_long and not (max(take_profits) < entry < stop_loss):
            return False, "Invalid SHORT/SELL stop-loss or take-profit ordering"
        leverage = self._effective_leverage(signal)
        if leverage < 1:
            return False, "Invalid leverage"
        positions = self._get_positions(market)
        # Pending limit orders reserve a position slot and prevent duplicate
        # same-symbol exposure before they are filled.
        exposure = dict(positions)
        exposure.update({
            order_id: {
                "symbol": order.get("symbol"),
                "status": "OPEN",
            }
            for order_id, order in self.open_orders.items()
            if order.get("market") == market and order.get("status") == "OPEN"
        })

        # Check total position limit using risk manager
        max_positions = MAX_SPOT_POSITIONS if market == "SPOT" else MAX_FUTURES_POSITIONS
        if not self.risk_manager.check_position_limit(exposure, max_positions):
            return False, f"Max {market} positions reached"

        # Check per-symbol position limit
        if not self.risk_manager.check_symbol_exposure(exposure, symbol):
            return False, f"Position already open for {signal['symbol']} on {market}"

        # Risk manager - daily loss check
        total_balance = self._get_total_equity()
        if not self.risk_manager.check_daily_loss(self.get_daily_pnl(), total_balance):
            return False, "Daily loss limit exceeded"

        # Risk manager check
        balance = self._available_balance(market)
        qty = self._calculate_quantity(balance, risk_amount, leverage, float(entry), market)
        if qty <= 0:
            return False, "Calculated quantity is zero"
        # Leverage
        # Total open risk includes the leverage multiplier used by P&L.
        total_risk = self._get_total_risk()
        new_risk = risk_amount * qty * leverage
        if not self.risk_manager.check_total_risk(total_risk, new_risk, total_balance):
            return False, "Total open risk limit exceeded"
        return True, "OK"

    async def execute_signal(self, signal: dict[str, Any]) -> str | None:
        """Execute a validated signal into a paper position."""
        ok, reason = self.validate_new_position(signal)
        if not ok:
            logger.warning("Signal %s risk check failed: %s", signal.get("signal_id", "unknown"), reason)
            return None
        market = signal["market"]
        balance = self._available_balance(market)
        risk_amount = abs(signal["entry"] - signal["stop_loss"])
        leverage = self._effective_leverage(signal)
        qty = self._calculate_quantity(balance, risk_amount, leverage, float(signal["entry"]), market)

        # Get realistic fill price with spread and slippage
        volume_24h = self._get_volume_24h(market, signal["symbol"])
        order_type = signal.get("order_type", "MARKET")
        fill_price = self.fee_calc.get_fill_price(
            market, signal["direction"], order_type, signal["entry"],
            qty, leverage, volume_24h
        )

        margin = qty * fill_price
        fee = self.fee_calc.calculate(market, signal["direction"], qty, fill_price, leverage)
        if margin + fee > balance:
            logger.warning("Insufficient %s paper balance for %s", market, signal["symbol"])
            return None
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
            "margin": margin,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
            "last_funding_time": (
                int(datetime.now(timezone.utc).timestamp() * 1000)
                // (8 * 3600 * 1000)
            ) * (8 * 3600 * 1000),
            "order_type": order_type,
            "signal_id": signal.get("signal_id"),
            "strategy": signal.get("strategy", "UNKNOWN"),
        }
        if market == "SPOT":
            self.spot_positions[position_id] = position
            self.spot_balance -= margin + fee
        else:
            self.futures_positions[position_id] = position
            self.futures_balance -= margin + fee
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
                alert_type="MARGIN_RISK",
                message=f"Position {position['symbol']} near liquidation",
                margin_ratio=margin_ratio,
                mark_price=mark_price,
                liquidation_price=self.liquidation.calculate_liquidation_price(position),
            ))

        if self.liquidation.check_liquidation(position, mark_price):
            liq_price = self.liquidation.calculate_liquidation_price(position)
            logger.warning("LIQUIDATION triggered for %s %s @ %.4f (liq: %.4f)",
                          position["symbol"], position["side"], mark_price, liq_price)
            await self._close_position(position, mark_price, "LIQUIDATION")
            await self.event_bus.publish(make_event(
                EventType.RISK_ALERT, "simulator",
                symbol=position["symbol"], market=position["market"],
                alert_type="LIQUIDATION",
                message=f"Position {position['symbol']} liquidated",
                liquidation_price=liq_price,
                mark_price=mark_price,
            ))

    async def _apply_funding(self, position: dict, funding_rate: float) -> None:
        """Apply funding payment to futures position."""
        interval_ms = 8 * 3600 * 1000
        current_bucket = (
            int(datetime.now(timezone.utc).timestamp() * 1000) // interval_ms
        ) * interval_ms
        last_funding = int(position.get("last_funding_time", current_bucket))
        if current_bucket <= last_funding:
            return

        # Catch up missed settlement boundaries after a temporary disconnect.
        # The latest observed rate is used for missed intervals because historical
        # funding rates are not currently stored by the market data layer.
        settlements = (current_bucket - last_funding) // interval_ms
        for _ in range(settlements):
            payment = self.funding_calc.calculate(position, funding_rate)
            position["fees_paid"] += payment
            if position["market"] == "FUTURES":
                self.futures_balance -= payment
        position["last_funding_time"] = current_bucket
        logger.debug(
            "Applied %d funding settlement(s) for %s at rate %.6f",
            settlements, position["symbol"], funding_rate,
        )

    async def _close_position(self, position: dict, exit_price: float, reason: str) -> None:
        market = position["market"]
        # Get realistic fill price with spread and slippage on exit
        volume_24h = self._get_volume_24h(market, position["symbol"])
        # Stop-loss/take-profit exits are market executions even when entry
        # was a limit order; they must still pay spread and slippage.
        fill_price = self.fee_calc.get_fill_price(
            market, position["side"], "MARKET", exit_price,
            position["amount"], position["leverage"], volume_24h
        )

        pnl = self.pnl_calc.realized(position, fill_price)
        fee = self.fee_calc.calculate(market, position["side"], position["amount"], fill_price, position["leverage"])
        margin = float(position.get("margin", position["entry_price"] * position["amount"]))
        # Isolated paper margin cannot create a negative account balance, even
        # when a stop/liquidation gap jumps past the reserved collateral.
        pnl = max(pnl, -margin)
        balance_delta = max(0.0, margin + pnl - fee)
        trade_pnl = balance_delta - margin - position.get("fees_paid", 0.0)
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
            logger.warning("Limit order %s risk check failed: %s", signal.get("signal_id", "unknown"), reason)
            return None

        market = signal["market"]
        balance = self._available_balance(market)
        risk_amount = abs(signal["entry"] - signal["stop_loss"])
        leverage = self._effective_leverage(signal)
        qty = self._calculate_quantity(balance, risk_amount, leverage, float(signal["entry"]), market)

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
                # Remove this reservation before validation/execution so the
                # order does not block itself as an existing same-symbol order.
                self.open_orders.pop(order["order_id"], None)
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
                position_id = await self.execute_signal(signal)
                order["status"] = "FILLED" if position_id else "REJECTED"
                order["position_id"] = position_id
                event_type = EventType.ORDER_FILLED if position_id else EventType.TRADE_REJECTED
                await self.event_bus.publish(make_event(
                    event_type, "simulator",
                    symbol=order["symbol"], market=order["market"],
                    order=order,
                    reason=None if position_id else "Risk validation failed at fill time",
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
        """Restore account state, normalizing timestamps serialized as ISO strings."""
        def parse_datetime(value):
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    return None
            return value

        self.spot_balance = float(state.get("spot_balance", SPOT_INITIAL_BALANCE))
        self.futures_balance = float(state.get("futures_balance", FUTURES_INITIAL_BALANCE))
        self.spot_positions = state.get("spot_positions", {})
        self.futures_positions = state.get("futures_positions", {})
        self.open_orders = state.get("open_orders", {})
        self.closed_trades = state.get("closed_trades", [])
        for position in list(self.spot_positions.values()) + list(self.futures_positions.values()):
            position["opened_at"] = parse_datetime(position.get("opened_at"))
        for order in self.open_orders.values():
            order["created_at"] = parse_datetime(order.get("created_at"))
        for trade in self.closed_trades:
            trade["opened_at"] = parse_datetime(trade.get("opened_at"))
            trade["closed_at"] = parse_datetime(trade.get("closed_at"))
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