"""Local market intelligence assistant API."""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from ...assistant_runtime import execute_assistant_query

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    symbol: str = Field(default="BTCUSDT", min_length=2, max_length=20)
    market: str = Field(default="SPOT", min_length=4, max_length=7)
    timeframe: str = Field(default="1h", min_length=2, max_length=3)


@router.post("/query")
async def query_assistant(request: AssistantQuery):
    try:
        result = await execute_assistant_query(
            get_bridge(),
            request.query,
            request.symbol,
            request.market,
            request.timeframe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "answer": result.answer,
        "tool": result.tool,
        "status": result.status,
        "sources": list(result.sources),
        "data": result.data,
        "task": {
            "id": result.task_id,
            "state": result.task_state,
            "trace": list(result.task_trace),
        },
        "disclaimer": (
            "Evidence is limited to returned local application data. "
            "Observations and calculations are not guaranteed predictions "
            "or trade instructions."
        ),
    }
