"""Positions API routes."""
from __future__ import annotations

from fastapi import APIRouter

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import PositionListResponse, PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=PositionListResponse)
async def get_positions():
    """Get all open positions."""
    bridge = get_bridge()
    positions = bridge.get_open_positions()
    spot = [p for p in positions if p["market"] == "SPOT"]
    futures = [p for p in positions if p["market"] == "FUTURES"]
    total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    total_fees = sum(p.get("fees_paid", 0) for p in positions)

    return PositionListResponse(
        positions=[PositionResponse(**p) for p in positions],
        total=len(positions),
        spot_count=len(spot),
        futures_count=len(futures),
        total_unrealized_pnl=total_unrealized,
        total_fees_paid=total_fees,
    )


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: str):
    """Get a specific position by ID."""
    bridge = get_bridge()
    positions = bridge.get_open_positions()
    for pos in positions:
        if pos["position_id"] == position_id:
            return PositionResponse(**pos)
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Position not found")