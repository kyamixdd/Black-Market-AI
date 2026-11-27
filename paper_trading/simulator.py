"""Paper trading simulator: virtual accounts, orders, positions, P&L."""
from __future__ import annotations

import asyncio
import logging
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from config import (
    FUTURES_INITIAL_BALANCE,
    MAX_FUTURES_POSITIONS,
    MAX_SPOT_POSITIONS,
    RISK_MAX_DAILY_LOSS_PCT,
    RISK_MAX_LEVERAGE,
    RISK_MAX_POSITION_SIZE_PCT,
    RISK_MAX_ASSET_EXPOSURE_PCT,
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
from core.observability import log_event

logger = logging.getLogger(__name__)


class Simulator:
    def __init__(self, event_bus: EventBus, market_cache=None):
        self.event_bus = event_bus
        self.market_cache = market_cache
        self.persist_order_callback = None
        self.persist_position_callback = None
        self.persist_trade_callback = None
        self.persist_partial_trade_callback = None
        self._account_lock = asyncio.Lock()
        self.initial_spot_balance = SPOT_INITIAL_BALANCE
        self.initial_futures_balance = FUTURES_INITIAL_BALANCE
        self.spot_balance = self.initial_spot_balance
        self.futures_balance = self.initial_futures_balance
        self.spot_positions: dict[str, dict] = {}
        self.futures_positions: dict[str, dict] = {}
        self.open_orders: dict[str, dict] = {}
        self.closed_trades: list[dict] = []
        self.daily_pnl = 0.0  # realized net P&L ledger
        self.daily_pnl_date = datetime.now(timezone.utc).date()
        self.daily_start_equity = self.initial_spot_balance + self.initial_futures_balance
        self.daily_equity_state_loaded = False
        self.persist_daily_equity_callback = None
        self.fee_calc = FeeCalculator()
        self.funding_calc = FundingCalculator()
        self.liquidation = LiquidationEngine()
        self.pnl_calc = PnLCalculator()
        self.adaptive_risk = None
        self.risk_manager = RiskManager(
            max_risk_pct=RISK_PER_TRADE_PCT,
            max_daily_loss_pct=RISK_MAX_DAILY_LOSS_PCT,
            max_open_risk_pct=RISK_MAX_TOTAL_OPEN_PCT,
            max_leverage=RISK_MAX_LEVERAGE,
            max_spot_positions=MAX_SPOT_POSITIONS,
            max_futures_positions=MAX_FUTURES_POSITIONS,
            max_position_size_pct=RISK_MAX_POSITION_SIZE_PCT,
            max_asset_exposure_pct=RISK_MAX_ASSET_EXPOSURE_PCT,
        )

    def get_balance(self, market: str) -> float:
        return self.spot_balance if market == "SPOT" else self.futures_balance

    def get_account_equity_breakdown(self) -> dict[str, float]:
        """Return available cash, allocated collateral, and mark-to-market equity.

        Opening a position moves cash into reserved Spot principal or Futures
        initial margin. Those amounts remain account assets; only fees and
        realized/unrealized losses reduce equity.
        """
        def sum_finite(values) -> float:
            total = 0.0
            for value in values:
                try:
                    number = float(value or 0.0)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(number):
                    total += number
            return total

        spot_positions = [
            p for p in self.spot_positions.values()
            if p.get("status", "OPEN") in ("OPEN", "CLOSING")
        ]
        futures_positions = [
            p for p in self.futures_positions.values()
            if p.get("status", "OPEN") in ("OPEN", "CLOSING")
        ]
        spot_reserved = sum_finite(
            p.get("reserved_notional", float(p.get("entry_price", 0.0)) * float(p.get("amount", 0.0)))
            for p in spot_positions
        )
        futures_margin = sum_finite(
            (
                p.get("reserved_margin")
                if p.get("reserved_margin") is not None
                else (
                    float(p.get("entry_price", 0.0))
                    * float(p.get("amount", 0.0))
                    / max(float(p.get("leverage", 1.0)), 1.0)
                )
            )
            for p in futures_positions
        )
        spot_unrealized = sum_finite(p.get("unrealized_pnl", 0.0) for p in spot_positions)
        futures_unrealized = sum_finite(p.get("unrealized_pnl", 0.0) for p in futures_positions)
        spot_available = float(self.spot_balance)
        futures_available = float(self.futures_balance)
        spot_equity = spot_available + spot_reserved + spot_unrealized
        futures_equity = futures_available + futures_margin + futures_unrealized
        return {
            "spot_available_balance": spot_available,
            "futures_available_balance": futures_available,
            "total_available_balance": spot_available + futures_available,
            "spot_used_capital": spot_reserved,
            "futures_used_margin": futures_margin,
            "total_used_margin": futures_margin,
            "total_used_capital": spot_reserved + futures_margin,
            "spot_unrealized_pnl": spot_unrealized,
            "futures_unrealized_pnl": futures_unrealized,
            "spot_equity": spot_equity,
            "futures_equity": futures_equity,
            "total_equity": spot_equity + futures_equity,
        }


    def _persist_daily_equity_baseline(self) -> None:
        callback = self.persist_daily_equity_callback
        if callable(callback):
            callback(self.daily_pnl_date.isoformat(), float(self.daily_start_equity))

    def get_daily_equity_baseline(self) -> float:
        """Return the total-equity baseline for the current UTC day."""
        self.get_daily_pnl()
        return float(self.daily_start_equity)

    def get_daily_pnl(self) -> float:
        """Return current-day mark-to-market P&L, including unrealized losses."""
        today = datetime.now(timezone.utc).date()
        if self.daily_pnl_date != today:
            self.daily_pnl = 0.0
            self.daily_pnl_date = today
            self.daily_start_equity = self.get_account_equity_breakdown()["total_equity"]
            self.daily_equity_state_loaded = True
            self._persist_daily_equity_baseline()
        equity = self.get_account_equity_breakdown()["total_equity"]
        return float(equity) - float(self.daily_start_equity)

    def _get_positions(self, market: str) -> dict[str, dict]:
        return self.spot_positions if market == "SPOT" else self.futures_positions

    def _get_total_risk(self) -> float:
        total = 0.0
        groups = (self.spot_positions, self.futures_positions)
        for positions in groups:
            for pos in positions.values():
                if pos.get("status", "OPEN") not in ("OPEN", "CLOSING") or not pos.get("stop_loss"):
                    continue
                total += abs(float(pos["entry_price"]) - float(pos["stop_loss"])) * float(pos["amount"])
        for order in self.open_orders.values():
            if order.get("status") != "OPEN" or not order.get("stop_loss"):
                continue
            total += abs(float(order["entry_price"]) - float(order["stop_loss"])) * float(order["amount"])
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

    def _calc_fee(
        self,
        market: str,
        side: str,
        amount: float,
        price: float,
        leverage: float = 1.0,
        order_type: str = "MARKET",
    ) -> float:
        """Call fee_calc.calculate with order_type, falling back for legacy 5-arg test mocks."""
        try:
            return float(self.fee_calc.calculate(market, side, amount, price, leverage, order_type=order_type))
        except TypeError:
            return float(self.fee_calc.calculate(market, side, amount, price, leverage))

    def _calculate_order_quantity(self, signal: dict[str, Any], balance: float) -> tuple[float, float]:
        """Size by stop risk, then cap Spot buys to available cash including fees."""
        entry = float(signal["entry"])
        stop_loss = float(signal["stop_loss"])
        risk_distance = abs(entry - stop_loss)
        if risk_distance <= 0 or balance <= 0:
            return 0.0, 1.0

        market = signal["market"]
        direction = signal["direction"]
        effective_risk_pct = (
            self.adaptive_risk.get_effective_risk_per_trade()
            if self.adaptive_risk is not None
            else self.risk_manager.max_risk_pct
        )
        leverage = self.risk_manager.validate_leverage(
            market, float(signal.get("leverage", 1.0))
        )
        if self.adaptive_risk is not None:
            leverage = self.adaptive_risk.get_effective_leverage(market, leverage)
        breakdown = self.get_account_equity_breakdown()
        market_equity = breakdown["spot_equity"] if market == "SPOT" else breakdown["futures_equity"]
        sizing_base = market_equity if math.isfinite(market_equity) and market_equity > 0 else balance
        quantity = self.risk_manager.calculate_position_size(sizing_base, risk_distance, max_risk_pct=effective_risk_pct)
        if market != "SPOT":
            return quantity, leverage
        if direction not in ("LONG", "BUY"):
            return 0.0, leverage

        volume_24h = self._get_volume_24h(market, signal["symbol"])
        order_type = signal.get("order_type", "MARKET")
        # Fill price depends on quantity through market-impact slippage. Recalculate
        # the affordable amount and include the Spot fee in the cash ceiling.
        for _ in range(4):
            if quantity <= 0:
                return 0.0, leverage
            fill_price = self.fee_calc.get_fill_price(
                market, direction, order_type,
                entry, quantity, 1.0, volume_24h
            )
            if fill_price <= 0:
                return 0.0, leverage
            fee_per_unit = self._calc_fee(
                market, direction, 1.0, fill_price, 1.0, order_type=order_type
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
        if market not in ("SPOT", "FUTURES") or signal.get("direction") not in ("BUY", "SELL", "LONG", "SHORT"):
            return False, "Unsupported market or direction"
        entry = float(signal.get("entry", 0.0))
        stop = float(signal.get("stop_loss", 0.0))
        if not math.isfinite(entry) or not math.isfinite(stop) or entry <= 0 or stop <= 0:
            return False, "Entry and stop-loss must be finite positive prices"
        direction = signal["direction"]
        if direction in ("BUY", "LONG") and stop >= entry:
            return False, "Long stop-loss must be below entry"
        if direction in ("SELL", "SHORT") and stop <= entry:
            return False, "Short stop-loss must be above entry"
        targets = signal.get("take_profit") or []
        if targets:
            target = float(targets[0])
            if not math.isfinite(target) or target <= 0:
                return False, "Take-profit must be a finite positive price"
            if direction in ("BUY", "LONG") and target <= entry:
                return False, "Long take-profit must be above entry"
            if direction in ("SELL", "SHORT") and target >= entry:
                return False, "Short take-profit must be below entry"
        positions = self._get_positions(market)
        pending = {
            order_id: order for order_id, order in self.open_orders.items()
            if order.get("market") == market and order.get("status") == "OPEN"
        }
        occupied = {**positions, **pending}

        # Pending limit orders reserve slots and symbol exposure until filled or cancelled.
        if self.adaptive_risk is not None:
            open_count = sum(1 for p in occupied.values() if p.get("status", "OPEN") in ("OPEN", "CLOSING"))
            allowed, adaptive_reason = self.adaptive_risk.can_open_position(market, open_count)
            if not allowed:
                return False, adaptive_reason
            max_positions = (
                self.adaptive_risk.effective_max_spot_positions
                if market == "SPOT"
                else self.adaptive_risk.effective_max_futures_positions
            )
        else:
            max_positions = self.risk_manager.max_spot_positions if market == "SPOT" else self.risk_manager.max_futures_positions
        if not self.risk_manager.check_position_limit(occupied, max_positions):
            return False, f"Max {market} positions reached"
        if not self.risk_manager.check_symbol_exposure(occupied, signal["symbol"]):
            return False, f"Position already open or pending for {signal['symbol']} on {market}"

        # Daily loss is total mark-to-market equity drawdown from the fixed
        # UTC-day opening baseline, not merely closed-trade P&L.
        daily_pnl = self.get_daily_pnl()
        daily_equity_baseline = self.get_daily_equity_baseline()
        total_balance = self.get_account_equity_breakdown()["total_equity"]
        if not self.risk_manager.check_daily_loss(daily_pnl, daily_equity_baseline):
            return False, "Daily loss limit exceeded"

        # Risk manager check
        balance = self.get_balance(market)
        risk_amount = abs(float(signal["entry"]) - float(signal["stop_loss"]))
        if risk_amount <= 0:
            return False, "Invalid stop loss"
        qty, leverage = self._calculate_order_quantity(signal, balance)
        if leverage < 1.0:
            return False, "Invalid leverage"
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
        if market == "FUTURES":
            entry = float(signal["entry"])
            fee = self.fee_calc.calculate("FUTURES", direction, qty, entry, leverage)
            required_margin = qty * entry / leverage
            if required_margin + fee > balance + 1e-9:
                return False, "Insufficient available Futures balance for margin and fees"
        # Enforce notional limits on actual intended entry and aggregate asset exposure.
        notional = qty * float(signal["entry"])
        if not self.risk_manager.check_position_notional(notional, total_balance):
            return False, "Maximum position size exceeded"
        exposure_positions = {
            **self.spot_positions, **self.futures_positions,
            **{oid: order for oid, order in self.open_orders.items() if order.get("status") == "OPEN"},
        }
        if not self.risk_manager.check_asset_exposure(
            exposure_positions, signal["symbol"], notional, total_balance,
        ):
            return False, "Maximum asset exposure exceeded"
        total_risk = self._get_total_risk()
        new_risk = risk_amount * qty
        if not self.risk_manager.check_total_risk(total_risk, new_risk, total_balance):
            return False, "Total open risk limit exceeded"
        return True, "OK"

    async def execute_signal(self, signal: dict[str, Any], quantity_override: float | None = None) -> str | None:
        """Serialize balance validation and collateral reservation."""
        started = time.perf_counter()
        try:
            async with self._account_lock:
                position_id = await self._execute_signal_locked(signal, quantity_override)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_event(
                logger, logging.ERROR, "paper_order_execution_failed",
                component="paper_trading", operation="execute_signal",
                market=signal.get("market"), symbol=signal.get("symbol"),
                outcome="FAILURE", exception_type=type(exc).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                recommendation="Inspect the simulator traceback and database_write_failed events; no live exchange order was submitted.",
            )
            raise
        log_event(
            logger,
            logging.INFO if position_id else logging.WARNING,
            "paper_order_execution_completed" if position_id else "paper_order_execution_rejected",
            component="paper_trading", operation="execute_signal",
            market=signal.get("market"), symbol=signal.get("symbol"),
            outcome="EXECUTED" if position_id else "REJECTED",
            details=f"position_id={position_id or 'none'}; paper_only=true",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            recommendation=None if position_id else "Review signal/risk rejection events and paper balance, market-data freshness, and position limits.",
        )
        return position_id

    async def _execute_signal_locked(self, signal: dict[str, Any], quantity_override: float | None = None) -> str | None:
        """Execute a signal while holding the account allocation lock.

        An order ID is the simulator's idempotency key. If recovery or a retry
        submits the same order again, return its existing open position and
        refuse to execute an already completed order a second time.
        """
        order_id = signal.get("order_id")
        if not order_id:
            signal_id = str(signal.get("signal_id", ""))
            order_id = (
                f"AUTO-{signal_id}"[:64]
                if signal_id and signal_id != "MANUAL"
                else f"ORD-{uuid.uuid4().hex[:16].upper()}"
            )
            signal["order_id"] = order_id
        if order_id:
            existing_position = next(
                (
                    position for position in (*self.spot_positions.values(), *self.futures_positions.values())
                    if position.get("order_id") == order_id and position.get("status") == "OPEN"
                ),
                None,
            )
            if existing_position is not None:
                return existing_position["position_id"]
            if any(trade.get("order_id") == order_id for trade in self.closed_trades):
                logger.warning("Order %s has already executed; duplicate execution blocked", order_id)
                return None

        ok, reason = self.validate_new_position(signal, quantity_override)
        if not ok:
            logger.warning("Signal %s risk check failed: %s", signal["signal_id"], reason)
            return None
        market = signal["market"]
        balance = self.get_balance(market)
        qty, leverage = self._calculate_order_quantity(signal, balance)
        leverage = self.risk_manager.validate_leverage(market, signal.get("leverage", 1.0))
        if leverage < 1.0 or (market == "SPOT" and leverage != 1.0):
            logger.warning("Order %s rejected: invalid market leverage", signal.get("signal_id"))
            return None
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

        # Adjust auto-sized orders for slippage-induced stop-distance changes.
        equity = self.get_account_equity_breakdown()["total_equity"]
        stop_price = float(signal["stop_loss"])
        actual_distance = abs(fill_price - stop_price)
        risk_budget = equity * self.risk_manager.max_risk_pct / 100.0 * 0.999
        if quantity_override is None and actual_distance > 0 and qty * actual_distance > risk_budget:
            qty = risk_budget / actual_distance
            fill_price = self.fee_calc.get_fill_price(
                market, signal["direction"], order_type, signal["entry"],
                qty, leverage, volume_24h
            )
        actual_risk = abs(fill_price - stop_price) * qty
        actual_notional = qty * fill_price
        risk_equity = self.get_account_equity_breakdown()["total_equity"]
        if not self.risk_manager.check_trade_risk(actual_risk, risk_equity):
            logger.warning("Order %s rejected: actual fill exceeds per-trade risk budget", signal.get("signal_id"))
            return None
        if not self.risk_manager.check_total_risk(self._get_total_risk(), actual_risk, risk_equity):
            logger.warning("Order %s rejected: actual fill exceeds aggregate open-risk cap", signal.get("signal_id"))
            return None
        if not self.risk_manager.check_position_notional(actual_notional, equity):
            logger.warning("Order %s rejected: actual fill exceeds position-size cap", signal.get("signal_id"))
            return None
        exposure_positions = {
            **self.spot_positions, **self.futures_positions,
            **{oid: order for oid, order in self.open_orders.items() if order.get("status") == "OPEN"},
        }
        if not self.risk_manager.check_asset_exposure(exposure_positions, signal["symbol"], actual_notional, equity):
            logger.warning("Order %s rejected: actual fill exceeds asset-exposure cap", signal.get("signal_id"))
            return None

        # Deduct fees upfront
        fee = self._calc_fee(market, signal["direction"], qty, fill_price, leverage, order_type=order_type)
        reserved_notional = qty * fill_price if market == "SPOT" else 0.0
        reserved_margin = qty * fill_price / leverage if market == "FUTURES" else 0.0
        pending_collateral = 0.0
        for pending in self.open_orders.values():
            if pending.get("status") != "OPEN" or pending.get("market") != market:
                continue
            pending_notional = float(pending["entry_price"]) * float(pending["amount"])
            pending_leverage = max(float(pending.get("leverage", 1.0)), 1.0)
            pending_fee = self._calc_fee(
                market, pending["side"], float(pending["amount"]),
                float(pending["entry_price"]), pending_leverage,
                order_type=pending.get("order_type", "LIMIT"),
            )
            pending_collateral += (
                pending_notional if market == "SPOT" else pending_notional / pending_leverage
            ) + pending_fee
        available_after_reservations = balance - pending_collateral
        if market == "FUTURES" and reserved_margin + fee > available_after_reservations + 1e-9:
            logger.warning("Futures order %s exceeds available margin after pending-order reservations", signal["signal_id"])
            return None
        if market == "SPOT" and reserved_notional + fee > available_after_reservations + 1e-9:
            logger.warning("Spot order %s exceeds available cash after pending-order reservations", signal["signal_id"])
            return None

        # Persist a recoverable order claim before mutating balances or opening
        # the position. Startup recovery moves an interrupted FILLING order to
        # RECOVERY_REVIEW unless its position/trade proves it completed.
        order_record = {
            "order_id": order_id,
            "signal_id": signal.get("signal_id"),
            "symbol": signal["symbol"],
            "market": market,
            "order_type": order_type,
            "side": signal["direction"],
            "amount": qty,
            "entry_price": fill_price,
            "price": fill_price,
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"][0] if signal["take_profit"] else None,
            "status": "FILLING",
            "filled_amount": 0.0,
            "avg_fill_price": 0.0,
            "fee": fee,
            "leverage": leverage,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            if order_type != "LIMIT" and callable(self.persist_order_callback):
                self.persist_order_callback(order_record)
        except Exception:
            logger.exception("Market paper order %s could not be durably claimed; execution aborted", order_id)
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
            "reserved_margin": reserved_margin,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
            "order_type": order_type,
            "signal_id": signal.get("signal_id"),
            "order_id": order_id,
            "strategy": signal.get("strategy", "UNKNOWN"),
            "max_favorable_excursion_pct": 0.0,
            "max_adverse_excursion_pct": 0.0,
            "decision_snapshot": json.dumps({
                key: signal.get(key) for key in (
                    "signal_id", "strategy", "direction", "entry", "stop_loss",
                    "take_profit", "confidence", "regime", "timeframe",
                    "reasons", "_model_evidence",
                ) if signal.get(key) is not None
            }, default=str),
            "risk_calculation_verified": True,
        }
        if market == "SPOT":
            self.spot_positions[position_id] = position
            self.spot_balance -= reserved_notional + fee
        else:
            self.futures_positions[position_id] = position
            self.futures_balance -= reserved_margin + fee

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
                self.futures_balance += reserved_margin + fee
            raise

        order_record.update({
            "status": "FILLED",
            "filled_amount": qty,
            "avg_fill_price": fill_price,
            "fee": fee,
        })
        try:
            if order_type != "LIMIT" and callable(self.persist_order_callback):
                self.persist_order_callback(order_record)
        except Exception:
            # Keep FILLING durable state for restart reconciliation; the
            # persisted position is authoritative evidence of completion.
            logger.exception("Position %s opened but order %s fill status needs recovery", position_id, order_id)
        else:
            order_record["_durably_persisted"] = True

        try:
            await self.event_bus.publish(make_event(
                EventType.POSITION_OPENED, "simulator",
                symbol=signal["symbol"], market=market, position=position
            ))
        except Exception:
            if not callable(self.persist_position_callback):
                raise
        try:
            await self.event_bus.publish(make_event(
                EventType.ORDER_FILLED, "simulator",
                symbol=signal["symbol"], market=market, order=order_record
            ))
        except Exception:
            if not callable(self.persist_order_callback):
                raise
            logger.exception("Paper order %s was filled but its Activity event could not be published", order_id)
            logger.exception("Position %s was persisted but its open event could not be published", position_id)
        logger.info("Opened %s position %s %s @ %.4f (fill: %.4f)", market, signal["direction"], signal["symbol"], signal["entry"], fill_price)
        return position_id

    async def update_prices(self, market: str, symbol: str, price: float,
                        mark_price: float | None = None, funding_rate: float | None = None) -> None:
        try:
            current = float(price)
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(current) or current <= 0:
            return
        try:
            mark = float(mark_price) if mark_price is not None else current
        except (TypeError, ValueError, OverflowError):
            mark = current
        if not math.isfinite(mark) or mark <= 0:
            mark = current
        if funding_rate is not None:
            try:
                funding_rate = float(funding_rate)
            except (TypeError, ValueError, OverflowError):
                funding_rate = None
            if funding_rate is not None and not math.isfinite(funding_rate):
                funding_rate = None
        price = current
        mark_price = mark
        async with self._account_lock:
            positions = self._get_positions(market)
            # Iterate over a copy to avoid "dictionary changed size during iteration"
            for pos in list(positions.values()):
                if pos["symbol"] == symbol and pos["status"] == "OPEN":
                    pos["current_price"] = price
                    pos["unrealized_pnl"] = self.pnl_calc.unrealized(pos, price)
                    entry = float(pos["entry_price"])
                    raw_return = ((price - entry) / entry * 100.0) if pos["side"] in ("LONG", "BUY") else ((entry - price) / entry * 100.0)
                    previous_mfe = float(pos.get("max_favorable_excursion_pct", 0.0))
                    previous_mae = float(pos.get("max_adverse_excursion_pct", 0.0))
                    pos["max_favorable_excursion_pct"] = max(previous_mfe, raw_return)
                    pos["max_adverse_excursion_pct"] = min(previous_mae, raw_return)
                    if callable(self.persist_position_callback) and (
                        pos["max_favorable_excursion_pct"] != previous_mfe
                        or pos["max_adverse_excursion_pct"] != previous_mae
                    ):
                        self.persist_position_callback(pos)

                    # Check liquidation first for futures
                    if market == "FUTURES" and pos["status"] == "OPEN":
                        await self._check_liquidation(pos, mark_price or price)

                    # Check stop/tp if still open
                    if pos["status"] == "OPEN":
                        await self._check_exit(pos, price, market)

                    # Apply funding if rate provided
                    if market == "FUTURES" and pos["status"] == "OPEN" and funding_rate is not None:
                        await self._apply_funding(pos, funding_rate, mark_price or price)

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
            try:
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
            except Exception:
                logger.exception("Could not publish pre-liquidation alert for %s", position["position_id"])

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

    async def _apply_funding(self, position: dict, funding_rate: float, mark_price: float | None = None) -> None:
        """Apply funding payment to futures position."""
        # Funding settles on fixed UTC boundaries (00:00, 08:00, 16:00),
        # not eight hours after the first market-data update seen by this process.
        now = datetime.now(timezone.utc)
        interval_ms = 8 * 3600 * 1000
        current_boundary_ms = (int(now.timestamp() * 1000) // interval_ms) * interval_ms
        last_funding = int(position.get("last_funding_time", 0) or 0)
        opened_at = position.get("opened_at")
        if isinstance(opened_at, datetime):
            opened_at_ms = int(
                (opened_at.replace(tzinfo=timezone.utc) if opened_at.tzinfo is None else opened_at)
                .timestamp() * 1000
            )
        else:
            opened_at_ms = 0

        # Do not charge immediately on the first price tick after opening. A
        # position becomes eligible at the first scheduled funding boundary
        # after it was opened. Persist the boundary itself to make retries and
        # restarts idempotent within that settlement interval.
        if current_boundary_ms <= last_funding or current_boundary_ms <= opened_at_ms:
            return

        payment = float(self.funding_calc.calculate(position, funding_rate, mark_price))
        if not math.isfinite(payment):
            raise ValueError("Funding payment must be finite.")

        # Persist the funding timestamp and fee adjustment together. Otherwise a
        # restart can forget the interval and charge the same funding payment twice.
        previous_fees = float(position.get("fees_paid", 0.0))
        previous_timestamp = last_funding
        previous_balance = self.futures_balance
        position["fees_paid"] = previous_fees + payment
        position["last_funding_time"] = current_boundary_ms
        self.futures_balance -= payment
        try:
            if callable(self.persist_position_callback):
                self.persist_position_callback(position)
        except Exception:
            position["fees_paid"] = previous_fees
            position["last_funding_time"] = previous_timestamp
            self.futures_balance = previous_balance
            raise
        logger.debug("Funding payment for %s: %.4f (rate: %.6f)", position["symbol"], payment, funding_rate)

    async def _partial_close_position(self, position: dict, exit_price: float, quantity: float, reason: str = "PARTIAL") -> bool:
        """Partially close a position, realizing proportional P&L and releasing collateral."""
        if position.get("status") != "OPEN":
            return False
        quantity = float(quantity)
        exit_price = float(exit_price)
        amount_before = float(position["amount"])
        if not math.isfinite(quantity) or quantity <= 0 or quantity >= amount_before:
            raise ValueError("Partial-close quantity must be positive and smaller than the open quantity.")
        if not math.isfinite(exit_price) or exit_price <= 0:
            raise ValueError("Exit price must be finite and positive.")

        position["status"] = "CLOSING"
        market = position["market"]
        ratio = quantity / amount_before
        try:
            fill_price = float(self.fee_calc.get_fill_price(
                market, position["side"], position.get("order_type", "MARKET"),
                exit_price, quantity, position["leverage"],
                self._get_volume_24h(market, position["symbol"])
            ))
            fee = float(self.fee_calc.calculate(market, position["side"], quantity, fill_price, position["leverage"]))
            gross_pnl = float(self.pnl_calc.realized({**position, "amount": quantity}, fill_price))
            allocated_entry_fees = float(position.get("fees_paid", 0.0)) * ratio
            net_pnl = gross_pnl - allocated_entry_fees - fee
            if not all(math.isfinite(v) for v in (fill_price, fee, gross_pnl, allocated_entry_fees, net_pnl)) or fill_price <= 0 or fee < 0:
                raise ValueError("Partial-close accounting produced invalid values.")
        except Exception:
            position["status"] = "OPEN"
            raise

        old = dict(position)
        balance_before = self.get_balance(market)
        daily_before = self.daily_pnl
        collateral_key = "reserved_notional" if market == "SPOT" else "reserved_margin"
        collateral = float(position.get(collateral_key, 0.0))
        released = collateral * ratio
        if market == "SPOT":
            self.spot_balance += released + gross_pnl - fee
        else:
            self.futures_balance += released + gross_pnl - fee

        position["amount"] = amount_before - quantity
        position[collateral_key] = collateral - released
        position["fees_paid"] = float(position.get("fees_paid", 0.0)) - allocated_entry_fees
        position["realized_pnl"] = float(position.get("realized_pnl", 0.0)) + net_pnl
        position["unrealized_pnl"] = self.pnl_calc.unrealized(position, position.get("current_price", position["entry_price"]))
        position["status"] = "OPEN"
        trade = {
            "position_id": f"{position['position_id']}-PARTIAL-{uuid.uuid4().hex[:8].upper()}",
            "source_position_id": position["position_id"],
            "symbol": position["symbol"], "market": market, "side": position["side"],
            "entry_price": position["entry_price"], "exit_price": fill_price,
            "amount": quantity, "leverage": position["leverage"], "pnl": net_pnl,
            "pnl_pct": net_pnl / (position["entry_price"] * quantity) * 100,
            "fee": allocated_entry_fees + fee, "strategy": position.get("strategy", "UNKNOWN"),
            "signal_id": position.get("signal_id"), "order_id": position.get("order_id"),
            "opened_at": position["opened_at"], "closed_at": datetime.now(timezone.utc),
            "close_reason": reason,
            "max_favorable_excursion_pct": position.get("max_favorable_excursion_pct", 0.0),
            "max_adverse_excursion_pct": position.get("max_adverse_excursion_pct", 0.0),
            "decision_snapshot": position.get("decision_snapshot"),
            "risk_calculation_verified": position.get("risk_calculation_verified"),
        }
        direction = str(position.get("side", "")).upper()
        plan_text = position.get("decision_snapshot")
        try:
            plan = json.loads(plan_text) if plan_text else {}
        except (TypeError, json.JSONDecodeError):
            plan = {}
        model = plan.get("_model_evidence") or {}
        predicted = str(model.get("predicted_class", "")).upper()
        result_return = (fill_price - float(position["entry_price"])) / float(position["entry_price"])
        if direction in {"SHORT", "SELL"}:
            result_return *= -1
        trade["prediction_correct"] = (predicted == ("UP" if result_return > 0 else "DOWN")) if predicted in {"UP", "DOWN"} and result_return != 0 else None
        gross_independent = (float(fill_price) - float(position["entry_price"])) * float(quantity)
        if direction in {"SHORT", "SELL"}:
            gross_independent *= -1
        independent_net = gross_independent - allocated_entry_fees - fee
        discrepancy = abs(independent_net - net_pnl) > max(0.01, abs(net_pnl) * 1e-8)
        trade["risk_calculation_verified"] = not discrepancy
        trade["calculation_audit_json"] = json.dumps({
            "gross_pnl_from_fill": gross_independent,
            "entry_fees": allocated_entry_fees,
            "exit_fee": fee,
            "recorded_net_pnl": net_pnl,
            "independent_net_pnl": independent_net,
            "status": "DISCREPANCY" if discrepancy else "VERIFIED",
        }, sort_keys=True)
        if discrepancy:
            logger.error("Partial trade accounting discrepancy detected for %s; original PnL retained and outcome flagged", position["position_id"])
        self.closed_trades.append(trade)
        self.get_daily_pnl()
        self.daily_pnl += net_pnl
        try:
            if callable(self.persist_partial_trade_callback):
                self.persist_partial_trade_callback(trade, position)
            elif callable(self.persist_position_callback):
                self.persist_position_callback(position)
        except Exception:
            self.closed_trades.pop()
            self.daily_pnl = daily_before
            if market == "SPOT":
                self.spot_balance = balance_before
            else:
                self.futures_balance = balance_before
            position.clear()
            position.update(old)
            raise
        try:
            await self.event_bus.publish(make_event(
                EventType.POSITION_CLOSED, "simulator",
                symbol=position["symbol"], market=market, trade=trade,
                payload={"partial": True, "remaining_amount": position["amount"]}
            ))
        except Exception:
            logger.exception("Partial close committed but event publication failed")
        return True

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
            if reason == "LIQUIDATION" and market == "FUTURES":
                reserved_margin = float(position.get(
                    "reserved_margin",
                    position["entry_price"] * position["amount"] / max(float(position.get("leverage", 1.0)), 1.0),
                ))
                if balance_delta < -reserved_margin:
                    balance_delta = -reserved_margin
                    pnl = balance_delta + fee
                    trade_pnl = balance_delta - float(position.get("fees_paid", 0.0))
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
            reserved_margin = float(position.get(
                "reserved_margin",
                position["entry_price"] * position["amount"] / max(float(position.get("leverage", 1.0)), 1.0),
            ))
            self.futures_balance += reserved_margin + balance_delta
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
            "max_favorable_excursion_pct": position.get("max_favorable_excursion_pct", 0.0),
            "max_adverse_excursion_pct": position.get("max_adverse_excursion_pct", 0.0),
            "decision_snapshot": position.get("decision_snapshot"),
        }
        direction = str(position.get("side", "")).upper()
        try:
            plan = json.loads(position.get("decision_snapshot") or "{}")
        except (TypeError, json.JSONDecodeError):
            plan = {}
        model = plan.get("_model_evidence") or {}
        predicted = str(model.get("predicted_class", "")).upper()
        result_return = (float(fill_price) - float(position["entry_price"])) / float(position["entry_price"])
        if direction in {"SHORT", "SELL"}:
            result_return *= -1
        trade["prediction_correct"] = (predicted == ("UP" if result_return > 0 else "DOWN")) if predicted in {"UP", "DOWN"} and result_return != 0 else None
        gross_independent = (float(fill_price) - float(position["entry_price"])) * float(position["amount"])
        if direction in {"SHORT", "SELL"}:
            gross_independent *= -1
        independent_net = gross_independent - float(fees_paid_before_close) - fee
        discrepancy = abs(independent_net - trade_pnl) > max(0.01, abs(trade_pnl) * 1e-8)
        trade["risk_calculation_verified"] = not discrepancy
        trade["calculation_audit_json"] = json.dumps({
            "gross_pnl_from_fill": gross_independent,
            "entry_fees": float(fees_paid_before_close),
            "exit_fee": fee,
            "recorded_net_pnl": trade_pnl,
            "independent_net_pnl": independent_net,
            "status": "DISCREPANCY" if discrepancy else "VERIFIED",
        }, sort_keys=True)
        if discrepancy:
            logger.error("Trade accounting discrepancy detected for %s; original PnL retained and outcome flagged", position["position_id"])
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
        try:
            await self.event_bus.publish(make_event(
                EventType.POSITION_CLOSED, "simulator",
                symbol=position["symbol"], market=market, trade=trade
            ))
        except Exception:
            if not callable(self.persist_trade_callback):
                raise
            logger.exception("Trade %s was persisted but its close event could not be published", position["position_id"])
        logger.info("Closed %s %s PnL: %.2f (%s, fill: %.4f)", position["symbol"], position["side"], trade_pnl, reason, fill_price)
        return True

    async def close_riskiest_position(self) -> str | None:
        """Close the open position closest to liquidation (or worst unrealized loss)."""
        async with self._account_lock:
            candidates = [
                p for p in (*self.futures_positions.values(), *self.spot_positions.values())
                if p.get("status") == "OPEN"
            ]
            if not candidates:
                return None

            def _risk_score(pos: dict) -> tuple[int, float]:
                price = float(pos.get("current_price") or pos.get("entry_price") or 0.0)
                if pos.get("market") == "FUTURES" and price > 0:
                    return (0, float(self.liquidation.get_margin_ratio(pos, price)))
                return (1, float(pos.get("unrealized_pnl", 0.0)))

            riskiest = min(candidates, key=_risk_score)
            exit_price = float(riskiest.get("current_price") or riskiest.get("entry_price") or 0.0)
            if exit_price <= 0:
                return None
            closed = await self._close_position(riskiest, exit_price, "ADAPTIVE_RISK")
            return riskiest["position_id"] if closed else None

    # --- Limit Order Handling ---
    async def place_limit_order(self, signal: dict[str, Any], quantity_override: float | None = None) -> str | None:
        """Serialize risk validation and pending-order reservation."""
        async with self._account_lock:
            return await self._place_limit_order_locked(signal, quantity_override)

    async def _place_limit_order_locked(self, signal: dict[str, Any], quantity_override: float | None = None) -> str | None:
        """Place a simulated limit order while holding the account lock."""
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

        # Pending limit orders reserve available cash/margin as well as risk and slots.
        pending_collateral = 0.0
        for pending in self.open_orders.values():
            if pending.get("status") != "OPEN" or pending.get("market") != market:
                continue
            pending_notional = float(pending["entry_price"]) * float(pending["amount"])
            pending_leverage = max(float(pending.get("leverage", 1.0)), 1.0)
            pending_fee = self._calc_fee(
                market, pending["side"], float(pending["amount"]),
                float(pending["entry_price"]), pending_leverage,
                order_type=pending.get("order_type", "LIMIT"),
            )
            pending_collateral += (
                pending_notional if market == "SPOT" else pending_notional / pending_leverage
            ) + pending_fee
        notional = float(signal["entry"]) * qty
        fee = self._calc_fee(market, signal["direction"], qty, float(signal["entry"]), leverage, order_type="LIMIT")
        required_collateral = (notional if market == "SPOT" else notional / max(leverage, 1.0)) + fee
        if pending_collateral + required_collateral > balance + 1e-9:
            logger.warning("Limit order %s rejected: pending orders exceed available balance", signal["signal_id"])
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
        try:
            await self.event_bus.publish(make_event(
                EventType.ORDER_PLACED, "simulator",
                symbol=signal["symbol"], market=market, order=order
            ))
        except Exception:
            if not callable(self.persist_order_callback):
                raise
            logger.exception("Limit order %s was persisted but its placement event could not be published", order_id)
        logger.info("Placed LIMIT order %s %s %s @ %.4f", market, signal["direction"], signal["symbol"], signal["entry"])
        return order_id

    async def cancel_limit_order(self, order_id: str) -> dict | None:
        """Cancel an open simulated limit order exactly once."""
        async with self._account_lock:
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
            try:
                await self.event_bus.publish(make_event(
                    EventType.TRADE_CANCELLED, "simulator",
                    symbol=order["symbol"], market=order["market"], order=order,
                ))
            except Exception:
                if not callable(self.persist_order_callback):
                    raise
                logger.exception("Limit order %s was cancelled and persisted but its event could not be published", order_id)
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

        async with self._account_lock:
            candidates = list(self.open_orders.values())

        for order in candidates:
            async with self._account_lock:
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
                async with self._account_lock:
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
                    else:
                        order["status"] = "OPEN"
                        try:
                            if callable(self.persist_order_callback):
                                self.persist_order_callback(order)
                        except Exception:
                            logger.exception("Could not persist retryable OPEN state for order %s", order_id)
                        logger.exception("Limit order %s fill attempt failed; order remains open", order_id)
                if already_executed:
                    try:
                        await self.event_bus.publish(make_event(
                            EventType.ORDER_FILLED, "simulator",
                            symbol=order["symbol"], market=order["market"], order=order
                        ))
                    except Exception:
                        if not callable(self.persist_order_callback):
                            raise
                        logger.exception("Could not publish recovered fill event for order %s", order_id)
                continue

            if not position_id:
                async with self._account_lock:
                    order["status"] = "OPEN"
                    try:
                        if callable(self.persist_order_callback):
                            self.persist_order_callback(order)
                    except Exception:
                        logger.exception("Could not persist rejected-fill OPEN state for order %s", order["order_id"])
                logger.info("Limit order %s was not filled because execution validation rejected it", order["order_id"])
                continue

            async with self._account_lock:
                order["status"] = "FILLED"
                self.open_orders.pop(order["order_id"], None)
                try:
                    if callable(self.persist_order_callback):
                        self.persist_order_callback(order)
                except Exception:
                    # Position.order_id was persisted before execution; restart recovery
                    # can safely reconcile a stale FILLING order against that position.
                    logger.exception("Could not persist FILLED state for order %s", order["order_id"])
            try:
                await self.event_bus.publish(make_event(
                    EventType.ORDER_FILLED, "simulator",
                    symbol=order["symbol"], market=order["market"], order=order
                ))
            except Exception:
                if not callable(self.persist_order_callback):
                    raise
                logger.exception("Limit order %s was filled and persisted but its event could not be published", order["order_id"])

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
            "daily_start_equity": self.daily_start_equity,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore state from persistence."""
        self.spot_balance = state.get("spot_balance", SPOT_INITIAL_BALANCE)
        self.futures_balance = state.get("futures_balance", FUTURES_INITIAL_BALANCE)
        self.spot_positions = state.get("spot_positions", {})
        self.futures_positions = state.get("futures_positions", {})
        self.open_orders = state.get("open_orders", {})
        self.closed_trades = state.get("closed_trades", [])
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
        daily_pnl_date = state.get("daily_pnl_date")
        try:
            self.daily_pnl_date = datetime.fromisoformat(daily_pnl_date).date() if daily_pnl_date else datetime.now(timezone.utc).date()
        except (TypeError, ValueError):
            self.daily_pnl_date = datetime.now(timezone.utc).date()
        self.daily_pnl = state.get("daily_pnl", 0.0)
        restored_baseline = state.get("daily_start_equity")
        try:
            restored_baseline = float(restored_baseline)
        except (TypeError, ValueError, OverflowError):
            restored_baseline = None
        self.daily_start_equity = (
            restored_baseline
            if restored_baseline is not None and math.isfinite(restored_baseline) and restored_baseline > 0
            else self.get_account_equity_breakdown()["total_equity"]
        )
        self.daily_equity_state_loaded = restored_baseline is not None and math.isfinite(restored_baseline) and restored_baseline > 0
        self.get_daily_pnl()
        logger.info("Restored state: Spot=%.2f, Futures=%.2f, OpenPos=%d, Trades=%d",
                    self.spot_balance, self.futures_balance,
                    len(self.spot_positions) + len(self.futures_positions),
                    len(self.closed_trades))
