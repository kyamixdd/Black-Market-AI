"""Local market intelligence assistant API."""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from ...assistant_nlu import ContextSnapshot
from ...assistant_runtime import AssistantRuntimeError, execute_assistant_query

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    symbol: str = Field(default="BTCUSDT", min_length=2, max_length=20)
    market: str = Field(default="SPOT", min_length=4, max_length=7)
    timeframe: str = Field(default="1h", min_length=2, max_length=3)


@router.post("/query")
async def query_assistant(request: AssistantQuery):
    supplied_fields = getattr(request, "model_fields_set", getattr(request, "__fields_set__", set()))
    context = ContextSnapshot(
        symbol=request.symbol if "symbol" in supplied_fields else None,
        timeframe=request.timeframe if "timeframe" in supplied_fields else None,
    )
    try:
        result = await execute_assistant_query(
            get_bridge(), request.query, request.symbol, request.market,
            request.timeframe, context=context,
        )
    except AssistantRuntimeError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "message": str(exc),
                "task": {
                    "id": exc.task_id,
                    "state": exc.task_state,
                    "trace": list(exc.task_trace),
                },
            },
        ) from exc

    parsed = result.structured_request
    return {
        "answer": result.answer,
        "tool": result.tool,
        "status": result.status,
        "sources": list(result.sources),
        "data": result.data,
        "understanding": {
            "intents": [{"name": intent.name, "tool": intent.tool} for intent in parsed.intents] if parsed else [],
            "entities": parsed.entities if parsed else {},
            "parameters": parsed.parameters if parsed else {},
            "constraints": list(parsed.constraints) if parsed else [],
            "context_references": list(parsed.context_references) if parsed else [],
            "confidence": parsed.confidence.value if parsed else "low",
            "confidence_reasons": list(parsed.confidence_reasons) if parsed else [],
            "clarification_required": parsed.clarification_required if parsed else False,
        },
        "task": {"id": result.task_id, "state": result.task_state, "trace": list(result.task_trace)},
        "disclaimer": (
            "Evidence is limited to returned local application data. "
            "Observations and calculations are not guaranteed predictions or trade instructions."
        ),
    }
