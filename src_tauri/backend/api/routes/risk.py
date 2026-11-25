"""Risk management API routes."""
from __future__ import annotations

from fastapi import APIRouter

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import RiskAlertListResponse, RiskMetricsResponse

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/status", response_model=RiskMetricsResponse)
async def get_risk_status():
    """Get current risk metrics and status."""
    bridge = get_bridge()
    return bridge.get_risk_metrics()


@router.get("/alerts", response_model=RiskAlertListResponse)
async def get_risk_alerts():
    """Get recent risk alerts."""
    bridge = get_bridge()
    events = bridge.get_recent_events(limit=100)
    risk_events = [e for e in events if e.get("event_type") == "RISK_ALERT"]
    return {"alerts": risk_events, "total": len(risk_events)}