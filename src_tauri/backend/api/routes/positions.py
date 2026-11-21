"""Open paper-position API routes."""
from __future__ import annotations

import math
from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import (
    PositionListResponse, PositionResponse, PositionUpdateRequest,
    PartialCloseRequest, ManualActionResponse,
)
from .trades import _validated_snapshot_price

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=PositionListResponse)
async def get_positions():
    bridge = get_bridge()
    positions = bridge.get_open_positions()
    spot = [p for p in positions if p["market"] == "SPOT"]
    futures = [p for p in positions if p["market"] == "FUTURES"]
    return PositionListResponse(
        positions=[PositionResponse(**p) for p in positions],
        total=len(positions), spot_count=len(spot), futures_count=len(futures),
        total_unrealized_pnl=sum(p.get("unrealized_pnl", 0) for p in positions),
        total_fees_paid=sum(p.get("fees_paid", 0) for p in positions),
    )


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: str):
    for pos in get_bridge().get_open_positions():
        if pos["position_id"] == position_id:
            return PositionResponse(**pos)
    raise HTTPException(404, "Position not found")


@router.post("/{position_id}/close", response_model=ManualActionResponse)
async def close_position(position_id: str):
    bridge = get_bridge()
    simulator = bridge.simulator
    position = simulator.spot_positions.get(position_id) or simulator.futures_positions.get(position_id)
    if position is None or position.get("status") != "OPEN":
        raise HTTPException(404, "Open position not found.")
    snapshot = bridge.get_market_snapshot(position["symbol"], position["market"])
    price = _validated_snapshot_price(snapshot)
    closed = await simulator._close_position(position, price, "MANUAL")
    if not closed:
        raise HTTPException(409, "Position is already closing or has been closed.")
    return ManualActionResponse(success=True, id=position_id, message="Paper position closed.")


@router.post("/{position_id}/partial-close", response_model=ManualActionResponse)
async def partial_close_position(position_id: str, request: PartialCloseRequest):
    bridge = get_bridge()
    simulator = bridge.simulator
    position = simulator.spot_positions.get(position_id) or simulator.futures_positions.get(position_id)
    if position is None or position.get("status") != "OPEN":
        raise HTTPException(404, "Open position not found.")
    if request.quantity >= float(position["amount"]):
        raise HTTPException(422, "Partial-close quantity must be smaller than the open quantity.")
    price = _validated_snapshot_price(bridge.get_market_snapshot(position["symbol"], position["market"]))
    closed = await simulator._partial_close_position(position, price, request.quantity)
    if not closed:
        raise HTTPException(409, "Position is already closing or has been closed.")
    return ManualActionResponse(success=True, id=position_id, message="Position partially closed.")


@router.patch("/{position_id}", response_model=ManualActionResponse)
async def update_position(position_id: str, request: PositionUpdateRequest):
    simulator = get_bridge().simulator
    position = simulator.spot_positions.get(position_id) or simulator.futures_positions.get(position_id)
    if position is None or position.get("status") != "OPEN":
        raise HTTPException(404, "Open position not found.")
    if request.stop_loss is None and request.take_profit is None:
        raise HTTPException(422, "Provide a stop loss or take profit update.")
    current_price = float(position.get("current_price") or position["entry_price"])
    if not math.isfinite(current_price) or current_price <= 0:
        raise HTTPException(409, "A valid current position price is required.")
    long_side = position["side"] in ("LONG", "BUY")
    if request.stop_loss is not None and (
        (long_side and request.stop_loss >= current_price)
        or (not long_side and request.stop_loss <= current_price)
    ):
        raise HTTPException(422, "Stop loss must remain beyond the current market price.")
    if request.take_profit is not None and (
        (long_side and request.take_profit <= current_price)
        or (not long_side and request.take_profit >= current_price)
    ):
        raise HTTPException(422, "Take profit must remain beyond the current market price.")
    # Validate every supplied value before mutating either field, then persist
    # the complete position so restart recovery keeps the latest risk levels.
    old_stop_loss = position.get("stop_loss")
    old_take_profit = position.get("take_profit")
    if request.stop_loss is not None:
        position["stop_loss"] = request.stop_loss
    if request.take_profit is not None:
        position["take_profit"] = request.take_profit
    try:
        persist_position = getattr(simulator, "persist_position_callback", None)
        if callable(persist_position):
            persist_position(position)
    except Exception as exc:
        position["stop_loss"] = old_stop_loss
        position["take_profit"] = old_take_profit
        raise HTTPException(503, "Position risk levels could not be saved.") from exc
    return ManualActionResponse(success=True, id=position_id, message="Position risk levels updated.")
