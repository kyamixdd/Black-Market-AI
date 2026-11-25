"""Autonomous paper engine and Telegram controls."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from config import PAPER_TRADING_ENABLED, REAL_TRADING_ENABLED
from ...bridge.orchestrator_bridge import get_bridge

router = APIRouter(tags=["autonomous"])


class AutonomousControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.get("/autonomous/status")
async def autonomous_status():
    return get_bridge().orch.get_autonomous_status()


@router.get("/autonomous/decisions")
async def autonomous_decisions(limit: int = Query(50, ge=1, le=200)):
    bridge = get_bridge()
    decisions = bridge.orch.get_autonomous_decisions(limit)
    return {"decisions": decisions, "total": len(decisions)}


@router.post("/autonomous/control")
async def autonomous_control(request: AutonomousControlRequest):
    bridge = get_bridge()
    if REAL_TRADING_ENABLED or not PAPER_TRADING_ENABLED:
        raise HTTPException(status_code=409, detail="Autonomous execution is restricted to paper trading.")
    if request.enabled:
        status = bridge.orch.get_autonomous_status()
        readiness = [reason for reason in status.get("readiness_reasons", []) if reason != "backend_engine_stopped"]
        if readiness:
            raise HTTPException(status_code=409, detail="Autonomous entries cannot resume: " + ", ".join(readiness))
    try:
        bridge.update_settings({"autonomous_enabled": request.enabled})
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail="Autonomous state could not be persisted safely.") from exc
    return bridge.orch.get_autonomous_status()


@router.get("/telegram/status")
async def telegram_status():
    telegram = get_bridge().orch.telegram
    return telegram.status() if telegram else {
        "enabled": False, "configured": False, "connected": False,
        "authorized_chat_configured": False, "last_error": None,
    }


@router.post("/telegram/test")
async def telegram_test():
    telegram = get_bridge().orch.telegram
    if telegram is None:
        raise HTTPException(status_code=409, detail="Telegram notifications are disabled.")
    result = await telegram.test_connection()
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("reason", "Telegram connection test failed."))
    return result
