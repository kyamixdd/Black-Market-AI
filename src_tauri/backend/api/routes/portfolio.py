"""Portfolio API routes."""
from __future__ import annotations

from fastapi import APIRouter

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import PortfolioBalanceResponse

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioBalanceResponse)
@router.get("/balance", response_model=PortfolioBalanceResponse)
@router.get("/summary", response_model=PortfolioBalanceResponse)
async def get_portfolio_balance():
    """Get portfolio balance summary."""
    bridge = get_bridge()
    return bridge.get_portfolio_summary()

