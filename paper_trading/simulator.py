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
from paper_trading.fee_calculator import FeeCalculator
from paper_trading.funding_calculator import FundingCalculator
from paper_trading.liquidation_engine import LiquidationEngine
from paper_trading.pnl_calculator import PnLCalculator
from paper_trading.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class Simulator:
    def __init__(self, event_bus: EventBus, market_cache=None):
        self.event_bus = event_bus
        self.market_cache = market_cache
        self.persist_order_callback = None
        self.persist_position_callback = None
        self.persist_trade_callback = None
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
        """Return exchange quote-volume cached by the market scanner."""
        if self.market_cache is None:
            return 0.0
        volume = self.market_cache.get_volume(market, symbol)
        try:
            value = float(volume)
        except (TypeError, ValueError):
            return 0.0
        return value if value > 0 else 0.0

    def _calculate_order_quantity(self, signal: dict[str, Any], balance: float) -> tuple[float, float]:
        """Size by stop risk, then cap Spot buys to available cash including fees."""
        entry = float(signal["entry"])
        stop_loss = float(signal["stop_loss"])
        risk_distance = abs(entry - stop_loss)
        if risk_distance <= 0 or balance <= 0:
            return 0.0, 1.0

        market = signal["market"]
        direction = signal["direction"]
        leverage = self.risk_manager.validate_leverage(
            market, float(signal.get("leverage", 1.0))
        )
        quantity = self.risk_manager.calculate_position_size(balance, risk_distance)
        if market != "SPOT":
            return quantity, leverage
        if direction not in ("LONG", "BUY"):
            return 0.0, leverage

        volume_24h = self._get_volume_24h(market, signal["symbol"])
        # Fill price depends on quantity through market-impact slippage. Recalculate
        # the affordable amount and include the Spot taker fee in the cash ceiling.
        for _ in range(4):
            if quantity <= 0:
                return 0.0, leverage
            fill_price = self.fee_calc.get_fill_price(
                market, direction, signal.get("order_type", "MARKET"),
                entry, quantity, 1.0, volume_24h
            )
            if fill_price <= 0:
                return 0.0, leverage
            fee_per_unit = self.fee_calc.calculate(
                market, direction, 1.0, fill_price, 1.0
            )
            affordable = balance / (fill_price + fee_per_unit)
            capped = min(quantity, affordable)
            if abs(capped - quantity) <= max(1e-12, quantity * 1e-9):
                quantity = capped
                break
            quantity = capped
        return max(0.0, quantity), leverage

    def validate_new_position(self, signal: dict[str, Any], quantity_override: float | None = None) -> tuple[bool, str]:
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
        # Spot principal is held in open positions rather than free cash; include
        # it in account equity so open trades do not shrink the risk denominator.
        spot_position_value = sum(
            float(position.get("reserved_notional", position.get("entry_price", 0.0) * position.get("amount", 0.0)))
            for position in self.spot_positions.values()
            if position.get("status") == "OPEN"
        )
        total_balance = self.spot_balance + self.futures_balance + spot_position_value
        if not self.risk_manager.check_daily_loss(self.get_daily_pnl(), total_balance):
            return False, "Daily loss limit exceeded"

        # Risk manager check
        balance = self.get_balance(market)
        risk_amount = abs(float(signal["entry"]) - float(signal["stop_loss"]))
        if risk_amount <= 0:
            return False, "Invalid stop loss"
        qty, leverage = self._calculate_order_quantity(signal, balance)
        if quantity_override is not None:
            if quantity_override <= 0 or quantity_override > qty + 1e-9:
                return False, "Requested quantity exceeds risk-sized maximum"
            qty = float(quantity_override)
        if qty <= 0:
            return False, (
                "Spot short positions are not supported" if market == "SPOT"
                and signal.get("direction") not in ("LONG", "BUY")
                else "Calculated quantity is zero"
            )
        # Total open risk
        total_risk = self._get_total_risk()
        new_risk = risk_amount * qty
        if not self.risk_manager.check_total_risk(total_risk, new_risk, total_balance):
            return False, "Total open risk limit exceeded"
        return True, "OK"

    async def execute_signal(self, signal: dict[str, Any], quantity_override: float | None = None) -> str | None:
        """Execute a validated signal into a paper position."""
        ok, reason = self.validate_new_position(signal, quantity_override)
        if not ok:
            logger.warning("Signal %s risk check failed: %s", signal["signal_id"], reason)
            return None
        market = signal["market"]
        balance = self.get_balance(market)
        qty, leverage = self._calculate_order_quantity(signal, balance)
        if quantity_override is not None:
            qty = float(quantity_override)
        if qty <= 0:
            return None

        # Get realistic fill price with spread and slippage
        volume_24h = self._get_volume_24h(market, signal["symbol"])
        order_type = signal.get("order_type", "MARKET")
        fill_price = self.fee_calc.get_fill_price(
            market, signal["direction"], order_type, signal["entry"],
            qty, leverage, volume_24h
        )

        # Deduct fees upfront
        fee = self.fee_calc.calculate(market, signal["direction"], qty, fill_price, leverage)
        reserved_notional = qty * fill_price if market == "SPOT" else 0.0
        if market == "SPOT" and reserved_notional + fee > self.spot_balance + 1e-9:
            logger.warning("Spot order %s exceeds available cash after fees", signal["signal_id"])
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
            "reserved_notional": reserved_notional,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
            "order_type": order_type,
            "signal_id": signal.get("signal_id"),
            "order_id": signal.get("order_id"),
            "strategy": signal.get("strategy", "UNKNOWN"),
        }
        if market == "SPOT":
            self.spot_positions[position_id] = position
            self.spot_balance -= reserved_notional + fee
        else:
            self.futures_positions[position_id] = position
            self.futures_balance -= fee

        # Persist the position before publishing an event that may be delayed or lost.
        try:
            if callable(self.persist_position_callback):
                self.persist_position_callback(position)
        except Exception:
            if market == "SPOT":
                self.spot_positions.pop(position_id, None)
                self.spot_balance += reserved_notional + fee
            else:
                self.futures_positions.pop(position_id, None)
                self.futures_balance += fee
            raise

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

        if position.get("status") == "OPEN" and self.liquidation.check_liquidation(position, mark_price):
            liq_price = self.liquidation.calculate_liquidation_price(position)
            logger.warning("LIQUIDATION triggered for %s %s @ %.4f (liq: %.4f)",
                          position["symbol"], position["side"], mark_price, liq_price)
            closed = await self._close_position(position, mark_price, "LIQUIDATION")
            if closed:
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

    async def _close_position(self, position: dict, exit_price: float, reason: str) -> bool:
        """Close an open position once; concurrent close attempts become no-ops."""
        if position.get("status") != "OPEN":
            return False

        # Claim the position before any await so manual, stop, TP and liquidation
        # paths cannot realize the same position more than once.
        position["status"] = "CLOSING"
        market = position["market"]
        try:
            volume_24h = self._get_volume_24h(market, position["symbol"])
            order_type = position.get("order_type", "MARKET")
            fill_price = self.fee_calc.get_fill_price(
                market, position["side"], order_type, exit_price,
                position["amount"], position["leverage"], volume_24h
            )
            if not math.isfinite(float(fill_price)) or float(fill_price) <= 0:
                raise ValueError("Exit fill price must be finite and positive.")

            pnl = float(self.pnl_calc.realized(position, fill_price))
            fee = float(self.fee_calc.calculate(market, position["side"], position["amount"], fill_price, position["leverage"]))
            balance_delta = pnl - fee
            trade_pnl = pnl - position.get("fees_paid", 0.0) - fee
            if not all(math.isfinite(value) for value in (pnl, fee, balance_delta, trade_pnl)):
                raise ValueError("Close accounting produced a non-finite value.")
        except Exception:
            position["status"] = "OPEN"
            raise

        balance_before_close = self.get_balance(market)
        daily_pnl_before_close = self.daily_pnl
        daily_pnl_date_before_close = self.daily_pnl_date
        fees_paid_before_close = position.get("fees_paid", 0.0)
        realized_before_close = position.get("realized_pnl", 0.0)

        position["status"] = "CLOSED"
        position["closed_at"] = datetime.now(timezone.utc)
        position["close_price"] = fill_price
        position["realized_pnl"] = trade_pnl
        position["fees_paid"] += fee
        if market == "SPOT":
            # Release the entry principal, then apply price P&L and the exit fee.
            reserved = float(position.get(
                "reserved_notional", position["entry_price"] * position["amount"]
            ))
            self.spot_balance += reserved + balance_delta
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
            "order_id": position.get("order_id"),
            "opened_at": position["opened_at"],
            "closed_at": datetime.now(timezone.utc),
            "close_reason": reason,
        }
        self.closed_trades.append(trade)
        self.get_daily_pnl()
        self.daily_pnl += trade_pnl
        try:
            if callable(self.persist_trade_callback):
                self.persist_trade_callback(trade)
        except Exception:
            # Keep in-memory balances and position state aligned with the database
            # transaction when durable trade persistence fails.
            self.closed_trades.pop()
            self.daily_pnl = daily_pnl_before_close
            self.daily_pnl_date = daily_pnl_date_before_close
            if market == "SPOT":
                self.spot_balance = balance_before_close
            else:
                self.futures_balance = balance_before_close
            position["status"] = "OPEN"
            position["fees_paid"] = fees_paid_before_close
            position["realized_pnl"] = realized_before_close
            position.pop("closed_at", None)
            position.pop("close_price", None)
            raise
        del pos_dict[position["position_id"]]
        await self.event_bus.publish(make_event(
            EventType.POSITION_CLOSED, "simulator",
            symbol=position["symbol"], market=market, trade=trade
        ))
        logger.info("Closed %s %s PnL: %.2f (%s, fill: %.4f)", position["symbol"], position["side"], trade_pnl, reason, fill_price)
        return True

    # --- Limit Order Handling ---
    async def place_limit_order(self, signal: dict[str, Any], quantity_override: float | None = None) -> str | None:
        """Place a simulated limit order."""
        ok, reason = self.validate_new_position(signal, quantity_override)
        if not ok:
            logger.warning("Limit order %s risk check failed: %s", signal["signal_id"], reason)
            return None

        market = signal["market"]
        balance = self.get_balance(market)
        qty, leverage = self._calculate_order_quantity(signal, balance)
        if quantity_override is not None:
            qty = float(quantity_override)
        if qty <= 0:
            return None

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
            "quantity_override": qty,
        }
        self.open_orders[order_id] = order
        try:
            if callable(self.persist_order_callback):
                self.persist_order_callback(order)
        except Exception:
            self.open_orders.pop(order_id, None)
            raise
        await self.event_bus.publish(make_event(
            EventType.ORDER_PLACED, "simulator",
            symbol=signal["symbol"], market=market, order=order
        ))
        logger.info("Placed LIMIT order %s %s %s @ %.4f", market, signal["direction"], signal["symbol"], signal["entry"])
        return order_id

    async def cancel_limit_order(self, order_id: str) -> dict | None:
        """Cancel an open simulated limit order exactly once."""
        order = self.open_orders.get(order_id)
        if order is None or order.get("status") != "OPEN":
            return None

        order["status"] = "CANCELLED"
        try:
            if callable(self.persist_order_callback):
                self.persist_order_callback(order)
        except Exception:
            order["status"] = "OPEN"
            raise
        self.open_orders.pop(order_id, None)
        await self.event_bus.publish(make_event(
            EventType.TRADE_CANCELLED, "simulator",
            symbol=order["symbol"], market=order["market"], order=order,
        ))
        logger.info("Cancelled limit order %s", order_id)
        return order

    async def check_limit_orders(self, market: str, symbol: str, price: float) -> None:
        """Fill eligible limit orders without losing orders rejected at execution time."""
        try:
            current_price = float(price)
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(current_price) or current_price <= 0:
            return

        for order in list(self.open_orders.values()):
            if order["market"] != market or order["symbol"] != symbol or order.get("status") != "OPEN":
                continue

            side = order["side"]
            limit_price = float(order["entry_price"])
            hit = (
                side in ("LONG", "BUY") and current_price <= limit_price
            ) or (
                side in ("SHORT", "SELL") and current_price >= limit_price
            )
            if not hit:
                continue

            # Claim the order before awaiting execution so concurrent price updates
            # cannot create duplicate positions from the same pending order.
            order["status"] = "FILLING"
            try:
                if callable(self.persist_order_callback):
                    self.persist_order_callback(order)
            except Exception:
                order["status"] = "OPEN"
                logger.exception("Could not persist FILLING state for order %s; fill deferred", order["order_id"])
                continue
            signal = {
                "signal_id": order.get("signal_id", "LIMIT-" + order["order_id"]),
                "order_id": order["order_id"],
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
            try:
                position_id = await self.execute_signal(
                    signal, float(order.get("quantity_override", order["amount"]))
                )
            except Exception:
                # execute_signal may have committed the position before a later
                # event publication failed. Never retry if this order already
                # owns an open position or a closed trade.
                order_id = order["order_id"]
                already_executed = any(
                    position.get("order_id") == order_id
                    for position in (*self.spot_positions.values(), *self.futures_positions.values())
                ) or any(trade.get("order_id") == order_id for trade in self.closed_trades)
                if already_executed:
                    order["status"] = "FILLED"
                    self.open_orders.pop(order_id, None)
                    try:
                        if callable(self.persist_order_callback):
                            self.persist_order_callback(order)
                    except Exception:
                        logger.exception("Could not persist recovered FILLED state for order %s", order_id)
                    logger.exception("Limit order %s created a position before a later failure; marked filled", order_id)
                    try:
                        await self.event_bus.publish(make_event(
                            EventType.ORDER_FILLED, "simulator",
                            symbol=order["symbol"], market=order["market"], order=order
                        ))
                    except Exception:
                        logger.exception("Could not publish recovered fill event for order %s", order_id)
                else:
                    order["status"] = "OPEN"
                    try:
                        if callable(self.persist_order_callback):
                            self.persist_order_callback(order)
                    except Exception:
                        logger.exception("Could not persist retryable OPEN state for order %s", order_id)
                    logger.exception("Limit order %s fill attempt failed; order remains open", order_id)
                continue

            if not position_id:
                order["status"] = "OPEN"
                try:
                    if callable(self.persist_order_callback):
                        self.persist_order_callback(order)
                except Exception:
                    logger.exception("Could not persist rejected-fill OPEN state for order %s", order["order_id"])
                logger.info("Limit order %s was not filled because execution validation rejected it", order["order_id"])
                continue

            order["status"] = "FILLED"
            self.open_orders.pop(order["order_id"], None)
            try:
                if callable(self.persist_order_callback):
                    self.persist_order_callback(order)
            except Exception:
                # Position.order_id was persisted before execution; restart recovery
                # can safely reconcile a stale FILLING order against that position.
                logger.exception("Could not persist FILLED state for order %s", order["order_id"])
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
        # A crash during execution is ambiguous: the position may already have
        # been created even if the order's FILLED state was not persisted.
        # Hold for reconciliation rather than risking a duplicate fill.
        for order_id, order in list(self.open_orders.items()):
            if order.get("status") != "FILLING":
                continue
            already_executed = any(
                position.get("order_id") == order_id
                for position in (*self.spot_positions.values(), *self.futures_positions.values())
            ) or any(trade.get("order_id") == order_id for trade in self.closed_trades)
            if already_executed:
                order["status"] = "FILLED"
                self.open_orders.pop(order_id, None)
            else:
                order["status"] = "RECOVERY_REVIEW"
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