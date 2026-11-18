"""Learning API routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import (
    LearningStatusResponse,
    PredictionListResponse,
    PredictionResponse,
    ModelRegistryListResponse,
    ModelRegistryResponse,
)

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("", response_model=LearningStatusResponse)
@router.get("/status", response_model=LearningStatusResponse)
async def get_learning_status():
    """Get learning engine status."""
    bridge = get_bridge()
    return bridge.get_learning_status()


@router.get("/predictions", response_model=PredictionListResponse)
async def get_predictions(limit: int = Query(100, le=1000)):
    """Get recent predictions with outcomes."""
    bridge = get_bridge()
    predictions = bridge.get_recent_predictions(limit)
    resolved = [p for p in predictions if p.get("is_correct") is not None]
    correct = [p for p in resolved if p.get("is_correct")]
    accuracy = len(correct) / len(resolved) * 100 if resolved else 0

    return PredictionListResponse(
        predictions=[PredictionResponse(**p) for p in predictions],
        total=len(predictions),
        resolved_count=len(resolved),
        accuracy=accuracy,
    )


@router.get("/models", response_model=ModelRegistryListResponse)
async def get_models():
    """Get model registry."""
    bridge = get_bridge()
    models = bridge.get_model_registry()
    return ModelRegistryListResponse(models=[ModelRegistryResponse(**m) for m in models])