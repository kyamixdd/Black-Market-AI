"""Local market intelligence assistant API."""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from ..assistant_intelligence import execute_tool, optional_provider_interpretation, select_tool, summarize_result, validate_market, validate_symbol

router = APIRouter(prefix="/assistant", tags=["assistant"])

class AssistantQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    symbol: str = Field(default="BTCUSDT", min_length=2, max_length=20)
    market: str = Field(default="SPOT", min_length=4, max_length=7)
    timeframe: str = Field(default="1h", min_length=2, max_length=3)

@router.post("/query")
async def query_assistant(request: AssistantQuery):
    try:
        symbol = validate_symbol(request.symbol)
        market = validate_market(request.market)
        tool = select_tool(request.query)
        result = await execute_tool(get_bridge(), tool, symbol, market, request.timeframe)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    answer = summarize_result(request.query, result)
    interpretation = await optional_provider_interpretation(request.query, result)
    if interpretation:
        answer += "\\n\\nOptional provider interpretation (not verified facts): " + interpretation
    return {
        "answer": answer,
        "tool": result.get("tool"),
        "status": result.get("status"),
        "sources": [result.get("source", "local backend")],
        "data": result.get("data"),
        "disclaimer": "Evidence is limited to returned local application data. Observations and calculations are not guaranteed predictions or trade instructions.",
    }
