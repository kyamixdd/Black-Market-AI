"""Intelligence API routes."""
from __future__ import annotations

from fastapi import APIRouter

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import (
    IntelligenceSummaryResponse,
    StrategyMetricsListResponse,
    StrategyMetricsResponse,
    StrategyWeightResponse,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("", response_model=IntelligenceSummaryResponse)
async def get_intelligence_summary():
    """Get strategy evaluations and current strategy weights."""
    bridge = get_bridge()
    return IntelligenceSummaryResponse(
        strategies=[
            StrategyMetricsResponse(**metric)
            for metric in bridge.get_strategy_metrics()
        ],
        strategy_weights=bridge.get_strategy_weights(),
    )


@router.get("/strategies", response_model=StrategyMetricsListResponse)
async def get_strategy_metrics():
    """Get strategy performance metrics."""
    bridge = get_bridge()
    metrics = bridge.get_strategy_metrics()
    return StrategyMetricsListResponse(metrics=[StrategyMetricsResponse(**m) for m in metrics])


@router.get("/weights", response_model=dict[str, StrategyWeightResponse])
async def get_strategy_weights():
    """Get strategy weights by regime."""
    bridge = get_bridge()
    return bridge.get_strategy_weights()