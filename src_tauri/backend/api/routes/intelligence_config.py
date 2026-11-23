"""API endpoints for validated assistant intelligence configuration."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.intelligence_config import (
    IntelligenceConfig,
    IntelligenceMode,
    config_for_mode,
    get_runtime_intelligence_config,
    save_intelligence_config,
)

router = APIRouter(prefix="/settings/intelligence", tags=["settings", "intelligence"])


class IntelligenceConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: IntelligenceMode = IntelligenceMode.BALANCED
    max_tool_calls: int | None = Field(default=None, ge=1, le=3)
    memory_enabled: bool | None = None
    feedback_enabled: bool | None = None
    provider_enabled: bool | None = None
    response_detail: str | None = None


@router.get("", response_model=IntelligenceConfig)
async def get_intelligence_settings() -> IntelligenceConfig:
    try:
        return get_runtime_intelligence_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Intelligence configuration is invalid.") from exc


@router.put("", response_model=IntelligenceConfig)
async def update_intelligence_settings(request: IntelligenceConfigRequest) -> IntelligenceConfig:
    values = config_for_mode(request.mode).model_dump(mode="python")
    values.update(request.model_dump(exclude_unset=True, exclude_none=True))
    try:
        validated = IntelligenceConfig.model_validate(values)
        return save_intelligence_config(validated)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
