"""Trades API routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import TradeListResponse, TradeResponse, TradeStatisticsResponse

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("", response_model=TradeListResponse)
async def get_trades(limit: int = Query(100, le=1000)):
    """Get recent closed trades."""
    bridge = get_bridge()
    trades = bridge.get_recent_trades(limit)
    stats = bridge.get_trade_statistics()
    return TradeListResponse(
        trades=[TradeResponse(**t) for t in trades],
        total=stats.get("total", 0),
        total_pnl=stats.get("total_pnl", 0.0),
        win_rate=stats.get("win_rate", 0.0),
        profit_factor=stats.get("profit_factor", 0.0),
        max_drawdown_pct=stats.get("max_drawdown_pct", 0.0),
    )


@router.get("/stats", response_model=TradeStatisticsResponse)
async def get_trade_stats():
    """Get trade statistics."""
    bridge = get_bridge()
    return bridge.get_trade_statistics()