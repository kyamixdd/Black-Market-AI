"""Signals API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import SignalListResponse, SignalResponse, SignalStatisticsResponse

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=SignalListResponse)
async def get_all_signals():
    """Get all recent signals."""
    bridge = get_bridge()
    signals = bridge.get_all_signals()
    return SignalListResponse(signals=[SignalResponse(**s) for s in signals], total=len(signals))


@router.get("/market/{market}", response_model=SignalListResponse)
async def get_signals_by_market(market: str):
    """Get signals filtered by market (SPOT or FUTURES)."""
    bridge = get_bridge()
    signals = bridge.get_signals_by_market(market.upper())
    return SignalListResponse(signals=[SignalResponse(**s) for s in signals], total=len(signals))


@router.get("/strategy/{strategy}", response_model=SignalListResponse)
async def get_signals_by_strategy(strategy: str):
    """Get signals filtered by strategy."""
    bridge = get_bridge()
    signals = bridge.get_signals_by_strategy(strategy)
    return SignalListResponse(signals=[SignalResponse(**s) for s in signals], total=len(signals))


@router.get("/stats", response_model=SignalStatisticsResponse)
async def get_signal_stats():
    """Get signal statistics."""
    bridge = get_bridge()
    signals = bridge.get_all_signals()
    if not signals:
        return {"total": 0, "avg_confidence": 0, "by_direction": {}, "by_strategy": {}}

    total = len(signals)
    avg_conf = sum(s.get("confidence", 0) for s in signals) / total

    dirs = {}
    for s in signals:
        d = s.get("direction", "UNKNOWN")
        dirs[d] = dirs.get(d, 0) + 1

    strats = {}
    for s in signals:
        st = s.get("strategy", "UNKNOWN")
        strats[st] = strats.get(st, 0) + 1

    return {
        "total": total,
        "avg_confidence": avg_conf,
        "by_direction": dirs,
        "by_strategy": strats,
    }