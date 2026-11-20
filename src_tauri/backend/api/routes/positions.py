"""Open paper-position API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import (
    PositionListResponse, PositionResponse, PositionUpdateRequest,
    ManualActionResponse,
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


@router.patch("/{position_id}", response_model=ManualActionResponse)
async def update_position(position_id: str, request: PositionUpdateRequest):
    simulator = get_bridge().simulator
    position = simulator.spot_positions.get(position_id) or simulator.futures_positions.get(position_id)
    if position is None or position.get("status") != "OPEN":
        raise HTTPException(404, "Open position not found.")
    if request.stop_loss is None and request.take_profit is None:
        raise HTTPException(422, "Provide a stop loss or take profit update.")
    entry = float(position["entry_price"])
    long_side = position["side"] in ("LONG", "BUY")
    if request.stop_loss is not None and (
        (long_side and request.stop_loss >= entry)
        or (not long_side and request.stop_loss <= entry)
    ):
        raise HTTPException(422, "Stop loss is on the invalid side of entry.")
    if request.take_profit is not None and (
        (long_side and request.take_profit <= entry)
        or (not long_side and request.take_profit >= entry)
    ):
        raise HTTPException(422, "Take profit is on the invalid side of entry.")
    # Validate every supplied value before mutating either field.
    if request.stop_loss is not None:
        position["stop_loss"] = request.stop_loss
    if request.take_profit is not None:
        position["take_profit"] = request.take_profit
    return ManualActionResponse(success=True, id=position_id, message="Position risk levels updated.")
