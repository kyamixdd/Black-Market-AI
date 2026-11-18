"""Settings API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import SettingsResponse, SettingsRequest

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Get current settings."""
    bridge = get_bridge()
    return bridge.get_settings()


@router.post("", response_model=SettingsResponse)
async def update_settings(request: SettingsRequest):
    """Reject updates until a validated configuration persistence path exists."""
    bridge = get_bridge()
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    try:
        return bridge.update_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc