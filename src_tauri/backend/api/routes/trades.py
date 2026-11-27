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
async def get_trades(limit: int = Query(100, ge=1, le=1000)):
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


@router.get("/order-history")
async def get_order_history(limit: int = Query(100, ge=1, le=1000)):
    """Return persisted simulated order lifecycle records, including fills."""
    repo = get_bridge().repo
    orders = repo.get_order_history(limit=limit)
    return {
        "orders": [
            {
                "order_id": item.order_id,
                "signal_id": item.signal_id,
                "symbol": item.symbol,
                "market": item.market,
                "order_type": item.order_type,
                "side": item.side,
                "amount": item.amount,
                "price": item.price,
                "stop_loss": item.stop_loss,
                "take_profit": item.take_profit,
                "status": item.status,
                "filled_amount": item.filled_amount,
                "avg_fill_price": item.avg_fill_price,
                "fee": item.fee,
                "leverage": item.leverage,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in orders
        ],
        "total": len(orders),
    }


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
        log_event(logger, logging.INFO, "paper_order_placed", symbol=request.symbol, market=request.market.value, order_type="LIMIT")
        return ManualActionResponse(success=True, id=order_id, message="Limit order placed.")
    position_id = await simulator.execute_signal(signal, request.quantity)
    if not position_id:
        log_event(logger, logging.WARNING, "paper_order_rejected", symbol=request.symbol, market=request.market.value, order_type="MARKET", reason="risk_controls")
        raise HTTPException(409, "Trade rejected by paper-trading risk controls.")
    log_event(logger, logging.INFO, "paper_position_opened", symbol=request.symbol, market=request.market.value)
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


@router.get("/{position_id}/review")
async def review_closed_paper_trade(position_id: str):
    """Review an actual closed paper trade; never infer quality from its P&L."""
    import json
    from datetime import datetime, timezone
    from learning.trade_review import build_trade_review
    from market.regime_radar import classify_market_regime

    bridge = get_bridge()
    trade = next(
        (item for item in bridge._all_closed_trades()
         if str(item.get("position_id", "")) == position_id),
        None,
    )
    if trade is None:
        raise HTTPException(404, "Closed paper trade not found.")

    signal = None
    signal_id = trade.get("signal_id")
    if signal_id:
        row = bridge.repo.get_signal(signal_id)
        if row is not None:
            signal = {
                "signal_id": row.signal_id, "strategy": row.strategy,
                "direction": row.direction, "entry": row.entry,
                "stop_loss": row.stop_loss, "take_profit": row.take_profit,
                "reasons": row.reasons, "status": row.status,
                "timeframe": row.timeframe,
            }
            for key in ("take_profit", "reasons"):
                if isinstance(signal[key], str):
                    try:
                        signal[key] = json.loads(signal[key])
                    except (ValueError, TypeError):
                        pass

    regime = None
    opened_at = trade.get("opened_at")
    try:
        if isinstance(opened_at, str):
            opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        if isinstance(opened_at, datetime):
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=timezone.utc)
            end_ms = int(opened_at.timestamp() * 1000)
            candles = await bridge.get_candles(
                trade["symbol"], trade["market"], "1h", limit=100, end_time=end_ms,
            )
            regime = classify_market_regime(
                candles, symbol=trade["symbol"], market=trade["market"],
                timeframe="1h", expected_candles=100,
            )
            regime["as_of_entry"] = opened_at.isoformat()
    except (KeyError, TypeError, ValueError, OverflowError):
        regime = None

    return build_trade_review(trade, signal, regime)
