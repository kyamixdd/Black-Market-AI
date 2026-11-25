"""Activity / System Events API routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import SystemEventListResponse, SystemEventResponse

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=SystemEventListResponse)
async def get_activity(limit: int = Query(100, le=1000)):
    """Get recent system events."""
    bridge = get_bridge()
    events = bridge.get_recent_events(limit)
    return SystemEventListResponse(events=[SystemEventResponse(**e) for e in events], total=len(events))