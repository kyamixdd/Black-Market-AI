"""Local market intelligence assistant API."""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import Request
import hashlib
import re

from database.connection import get_session_maker
from database.repositories import Repository
from ...assistant_memory import build_memory_record, retrieve_relevant_memories, MemoryValidationError
from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from ...assistant_nlu import ContextSnapshot
from ...assistant_runtime import AssistantRuntimeError, execute_assistant_query

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantMemoryCreate(BaseModel):
    model_config = {"extra": "forbid"}
    content: str = Field(min_length=3, max_length=1200)
    memory_type: str = Field(default="semantic", pattern="^(working|episodic|semantic|procedural)$")
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=1.0, ge=0, le=1)
    tags: list[str] = Field(default_factory=list, max_length=12)
    ttl_days: int | None = Field(default=None, ge=1, le=365)


def _memory_owner(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    # The API bearer credential defines the local memory namespace; raw tokens are never persisted.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _memory_repository() -> Repository:
    return Repository(get_session_maker())


@router.post("/memories")
async def create_memory(request: Request, payload: AssistantMemoryCreate):
    owner_key = _memory_owner(request)
    try:
        record = build_memory_record(
            owner_key=owner_key, memory_type=payload.memory_type,
            content=payload.content, importance=payload.importance,
            confidence=payload.confidence, tags=payload.tags,
            ttl_days=payload.ttl_days,
        )
        saved = _memory_repository().save_assistant_memory(record)
    except MemoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "saved", "memory": saved}


@router.get("/memories")
async def list_memories(request: Request, query: str | None = None, limit: int = 8):
    owner_key = _memory_owner(request)
    repository = _memory_repository()
    repository.delete_expired_assistant_memories()
    if query:
        memories = retrieve_relevant_memories(repository, owner_key, query, limit=limit)
    else:
        memories = repository.retrieve_assistant_memories(owner_key, limit=limit)
    return {"memories": memories, "count": len(memories)}


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, request: Request):
    if not re.fullmatch(r"[a-f0-9]{32}", memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    deleted = _memory_repository().delete_assistant_memory(memory_id, _memory_owner(request))
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted", "memory_id": memory_id}


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str, request: Request):
    if not re.fullmatch(r"[a-f0-9]{32}", memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    memory = _memory_repository().get_assistant_memory(memory_id, _memory_owner(request))
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"memory": memory}



class AssistantQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    symbol: str = Field(default="BTCUSDT", min_length=2, max_length=20)
    market: str = Field(default="SPOT", min_length=4, max_length=7)
    timeframe: str = Field(default="1h", min_length=2, max_length=3)


@router.post("/query")
async def query_assistant(request: Request, payload: AssistantQuery):
    owner_key = _memory_owner(request)
    repository = _memory_repository()
    remember_match = re.match(r"^(?:please\s+)?remember(?:\s+that)?\s+(.+)$", payload.query.strip(), re.I)
    if remember_match:
        try:
            record = build_memory_record(
                owner_key=owner_key, memory_type="semantic", content=remember_match.group(1),
                source="user_explicit", importance=0.75, confidence=1.0,
            )
            saved = repository.save_assistant_memory(record)
        except MemoryValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"answer": "Saved that memory.", "status": "memory_saved", "memory": saved,
                "task": {"state": "completed", "trace": ["received", "memory_saved", "completed"]}}

    recall_match = re.match(r"^(?:what do you remember(?:\s+about)?|recall)\s*(.*)$", payload.query.strip(), re.I)
    if recall_match:
        memories = retrieve_relevant_memories(repository, owner_key, recall_match.group(1) or "user preferences", limit=8)
        answer = "Relevant saved memories: " + "; ".join(item["content"] for item in memories) if memories else "No relevant saved memories were found."
        return {"answer": answer, "status": "memory_retrieved", "memories": memories,
                "task": {"state": "completed", "trace": ["received", "memory_retrieved", "completed"]}}

    memory_context = retrieve_relevant_memories(repository, owner_key, payload.query, limit=5)
    supplied_fields = getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set()))
    context = ContextSnapshot(
        symbol=payload.symbol if "symbol" in supplied_fields else None,
        timeframe=payload.timeframe if "timeframe" in supplied_fields else None,
    )
    try:
        result = await execute_assistant_query(
            get_bridge(), payload.query, payload.symbol, payload.market,
            payload.timeframe, context=context,
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
        "memory_context": [{"memory_id": item["memory_id"], "memory_type": item["memory_type"], "content": item["content"], "relevance_score": item["relevance_score"]} for item in memory_context],
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
