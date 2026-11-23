"""Settings API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import SettingsResponse, SettingsRequest
from core.intelligence_config import (
    IntelligenceConfig,
    IntelligenceMode,
    config_for_mode,
    get_runtime_intelligence_config,
    save_intelligence_config,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Get current settings."""
    bridge = get_bridge()
    return bridge.get_settings()


@router.post("", response_model=SettingsResponse)
async def update_settings(request: SettingsRequest):
    """Validate, persist, and apply runtime settings."""
    bridge = get_bridge()
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    try:
        result = bridge.update_settings(updates)
        if updates.get("spot_enabled") is True:
            await bridge.orch._discovery.discover_spot()
        if updates.get("futures_enabled") is True:
            await bridge.orch._discovery.discover_futures()
        if updates.get("spot_enabled") is True or updates.get("futures_enabled") is True:
            bridge.repo.save_symbols(bridge.orch.registry.to_dicts())
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Settings could not be persisted safely.") from exc


class IntelligenceConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: IntelligenceMode = IntelligenceMode.BALANCED
    max_tool_calls: int | None = Field(default=None, ge=1, le=3)
    memory_enabled: bool | None = None
    feedback_enabled: bool | None = None
    provider_enabled: bool | None = None
    response_detail: str | None = None


@router.get("/intelligence", response_model=IntelligenceConfig)
async def get_intelligence_settings():
    try:
        return get_runtime_intelligence_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Intelligence configuration is invalid.") from exc


@router.put("/intelligence", response_model=IntelligenceConfig)
async def update_intelligence_settings(request: IntelligenceConfigRequest):
    values = config_for_mode(request.mode).model_dump(mode="python")
    values.update(request.model_dump(exclude_unset=True, exclude_none=True))
    try:
        validated = IntelligenceConfig.model_validate(values)
        return save_intelligence_config(validated)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
