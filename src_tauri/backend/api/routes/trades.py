"""Trade and manual paper-order API routes."""
from __future__ import annotations

import math
import logging
from fastapi import APIRouter, HTTPException, Query

from ...bridge.orchestrator_bridge import get_bridge
from core.observability import log_event
from .schemas import (
    TradeListResponse, TradeResponse, TradeStatisticsResponse,
    OpenOrderListResponse, ManualOrderRequest, ManualActionResponse,
)

router = APIRouter(prefix="/trades", tags=["trades"])
logger = logging.getLogger(__name__)


def _validated_snapshot_price(snapshot: dict | None) -> float:
    """Require a finite positive price from a sufficiently fresh market snapshot."""
    if not isinstance(snapshot, dict):
        raise HTTPException(409, "A fresh market price is required.")
    try:
        price = float(snapshot.get("price"))
        age = snapshot.get("data_age_seconds")
        age = float(age) if age is not None else None
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(409, "A fresh market price is required.")
    freshness = snapshot.get("data_freshness")
    if (
        not math.isfinite(price) or price <= 0
        or freshness not in ("LIVE", "DELAYED")
        or (age is not None and (not math.isfinite(age) or age > 300))
        or (age is None and freshness != "LIVE")
    ):
        raise HTTPException(409, "A fresh market price is required.")
    return price


def _validated_manual_signal(request: ManualOrderRequest, bridge):
    market = request.market.value
    side = request.side.upper()
    if market == "SPOT" and side not in ("BUY", "LONG"):
        raise HTTPException(422, "Spot paper trading supports BUY/LONG only; shorting requires Futures.")
    if market == "FUTURES" and side in ("BUY", "SELL"):
        side = "LONG" if side == "BUY" else "SHORT"
    if request.order_type == "LIMIT" and request.price is None:
        raise HTTPException(422, "Limit orders require a price.")
    snapshot = bridge.get_market_snapshot(request.symbol, market)
    market_price = _validated_snapshot_price(snapshot)
    entry = float(request.price) if request.order_type == "LIMIT" else market_price
    if request.stop_loss >= entry and side in ("BUY", "LONG"):
        raise HTTPException(422, "Stop loss must be below entry for a long position.")
    if request.stop_loss <= entry and side in ("SELL", "SHORT"):
        raise HTTPException(422, "Stop loss must be above entry for a short position.")
    if request.take_profit is not None:
        if request.take_profit <= entry and side in ("BUY", "LONG"):
            raise HTTPException(422, "Take profit must be above entry for a long position.")
        if request.take_profit >= entry and side in ("SELL", "SHORT"):
            raise HTTPException(422, "Take profit must be below entry for a short position.")
    simulator = bridge.simulator
    balance = simulator.get_balance(market)
    risk_qty = simulator.risk_manager.calculate_position_size(balance, abs(entry - request.stop_loss))
    if request.quantity > risk_qty + 1e-9:
        raise HTTPException(422, f"Quantity exceeds risk-sized maximum ({risk_qty:.8g}).")
    return {
        "signal_id": "MANUAL",
        "symbol": request.symbol,
        "market": market,
        "direction": side,
        "entry": entry,
        "stop_loss": request.stop_loss,
        "take_profit": [request.take_profit] if request.take_profit is not None else [],
        "leverage": request.leverage,
        "order_type": request.order_type,
        "strategy": "MANUAL",
        "quantity_override": request.quantity,
    }


@router.get("", response_model=TradeListResponse)
async def get_trades(limit: int = Query(100, le=1000)):
    bridge = get_bridge()
    trades = bridge.get_recent_trades(limit)
    stats = bridge.get_trade_statistics()
    return TradeListResponse(
        trades=[TradeResponse(**t) for t in trades],
        total=stats.get("total", 0), total_pnl=stats.get("total_pnl", 0.0),
        win_rate=stats.get("win_rate", 0.0), profit_factor=stats.get("profit_factor", 0.0),
        max_drawdown_pct=stats.get("max_drawdown_pct", 0.0),
    )


@router.get("/stats", response_model=TradeStatisticsResponse)
async def get_trade_stats():
    return get_bridge().get_trade_statistics()


@router.get("/orders", response_model=OpenOrderListResponse)
async def get_open_orders():
    simulator = get_bridge().simulator
    return OpenOrderListResponse(
        orders=list(simulator.open_orders.values()),
        total=len(simulator.open_orders),
    )


@router.post("", response_model=ManualActionResponse)
async def open_manual_trade(request: ManualOrderRequest):
    bridge = get_bridge()
    signal = _validated_manual_signal(request, bridge)
    simulator = bridge.simulator
    if request.order_type == "LIMIT":
        order_id = await simulator.place_limit_order(signal, request.quantity)
        if not order_id:
            log_event(logger, logging.WARNING, "paper_order_rejected", symbol=request.symbol, market=request.market.value, order_type="LIMIT", reason="risk_controls")
            raise HTTPException(409, "Order rejected by paper-trading risk controls.")
        log_event(logger, logging.INFO, "paper_order_placed", symbol=request.symbol, market=request.market.value, order_type="LIMIT", order_id=order_id)
        return ManualActionResponse(success=True, id=order_id, message="Limit order placed.")
    position_id = await simulator.execute_signal(signal, request.quantity)
    if not position_id:
        log_event(logger, logging.WARNING, "paper_order_rejected", symbol=request.symbol, market=request.market.value, order_type="MARKET", reason="risk_controls")
        raise HTTPException(409, "Trade rejected by paper-trading risk controls.")
    log_event(logger, logging.INFO, "paper_position_opened", symbol=request.symbol, market=request.market.value, position_id=position_id)
    return ManualActionResponse(success=True, id=position_id, message="Paper position opened.")


@router.delete("/orders/{order_id}", response_model=ManualActionResponse)
async def cancel_order(order_id: str):
    simulator = get_bridge().simulator
    order = simulator.open_orders.get(order_id)
    if order is None:
        raise HTTPException(404, "Open order not found.")
    if order.get("status") == "FILLING":
        raise HTTPException(409, "Order is already filling and can no longer be cancelled.")
    if order.get("status") == "RECOVERY_REVIEW":
        raise HTTPException(409, "Order requires restart reconciliation before it can be cancelled.")
    if order.get("status") != "OPEN":
        raise HTTPException(409, "Order is not in a cancellable state.")
    cancelled = await simulator.cancel_limit_order(order_id)
    if cancelled is None:
        raise HTTPException(409, "Order state changed before cancellation could complete.")
    log_event(logger, logging.INFO, "paper_order_cancelled", order_id=order_id)
    return ManualActionResponse(success=True, id=order_id, message="Order cancelled.")
