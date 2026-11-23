"""Local market intelligence assistant API."""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import Request
import hashlib
import asyncio
from uuid import uuid4
import re

from database.connection import get_session_maker
from database.repositories import Repository
from ...assistant_memory import build_memory_record, retrieve_relevant_memories, MemoryValidationError
from fastapi import APIRouter, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from ...assistant_nlu import ContextSnapshot
from ...assistant_runtime import AssistantRuntimeError, execute_assistant_query
from ...assistant_planning import TASK_EXECUTION_MANAGER

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



@router.get("/tools")
async def list_assistant_tools(request: Request):
    _memory_owner(request)
    return {"tools": create_default_registry().list_tools()}


_ASYNC_TASKS: dict[str, dict] = {}
_ASYNC_TASK_LIMIT = 128


class AssistantQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    symbol: str = Field(default="BTCUSDT", min_length=2, max_length=20)
    market: str = Field(default="SPOT", min_length=4, max_length=7)
    timeframe: str = Field(default="1h", min_length=2, max_length=3)



@router.post("/tasks", status_code=202)
async def start_assistant_task(request: Request, payload: AssistantQuery):
    owner_key = _memory_owner(request)
    terminal_states = {"completed", "failed", "partially_completed", "cancelled", "awaiting_clarification"}
    active = sum(1 for item in _ASYNC_TASKS.values() if item["state"] not in terminal_states)
    if active >= 16:
        raise HTTPException(status_code=429, detail="Assistant task capacity reached; retry after an active task finishes.")
    for old_id in list(_ASYNC_TASKS):
        if len(_ASYNC_TASKS) < _ASYNC_TASK_LIMIT:
            break
        if _ASYNC_TASKS[old_id]["state"] in terminal_states:
            _ASYNC_TASKS.pop(old_id, None)
    if len(_ASYNC_TASKS) >= _ASYNC_TASK_LIMIT:
        raise HTTPException(status_code=429, detail="Assistant task history is full; wait for completed records to be evicted.")
    task_id = uuid4().hex
    TASK_EXECUTION_MANAGER.register(task_id)
    _ASYNC_TASKS[task_id] = {"owner": owner_key, "state": "received", "result": None, "error": None}

    async def _run():
        record = _ASYNC_TASKS.get(task_id)
        if record is None:
            TASK_EXECUTION_MANAGER.unregister(task_id)
            return
        record["state"] = "running"
        try:
            result = await execute_assistant_query(
                get_bridge(), payload.query, payload.symbol, payload.market,
                payload.timeframe, task_id=task_id,
            )
            record["state"] = result.task_state
            record["result"] = {
                "answer": result.answer, "tool": result.tool, "status": result.status,
                "data": result.data, "sources": list(result.sources),
                "task": {"id": result.task_id, "state": result.task_state, "trace": list(result.task_trace)},
            }
        except AssistantRuntimeError as exc:
            record["state"] = exc.task_state
            record["error"] = {"code": exc.error_code, "message": str(exc)}
            record["task"] = {"id": task_id, "state": exc.task_state, "trace": list(exc.task_trace)}
        except Exception:
            record["state"] = "failed"
            record["error"] = {"code": "assistant_task_failed", "message": "Assistant task failed safely."}
        finally:
            TASK_EXECUTION_MANAGER.unregister(task_id)

    asyncio.create_task(_run())
    return {"task_id": task_id, "state": "received", "status_url": f"/api/assistant/tasks/{task_id}"}


@router.get("/tasks/{task_id}")
async def get_assistant_task(task_id: str, request: Request):
    owner_key = _memory_owner(request)
    record = _ASYNC_TASKS.get(task_id)
    if record is None or record["owner"] != owner_key:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "state": record["state"], "result": record.get("result"), "error": record.get("error")}


@router.post("/tasks/{task_id}/cancel")
async def cancel_assistant_task(task_id: str, request: Request):
    owner_key = _memory_owner(request)
    record = _ASYNC_TASKS.get(task_id)
    if record is None or record["owner"] != owner_key:
        raise HTTPException(status_code=404, detail="Task not found")
    if record["state"] not in {"received", "running"}:
        return {"task_id": task_id, "state": record["state"], "cancelled": False}
    cancelled = TASK_EXECUTION_MANAGER.cancel(task_id)
    if cancelled:
        record["state"] = "cancellation_requested"
    return {"task_id": task_id, "state": record["state"], "cancelled": cancelled}


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
                "code": exc.error_code,
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


class AssistantFeedbackCreate(BaseModel):
    model_config = {"extra": "forbid"}
    request_id: str = Field(min_length=8, max_length=64, pattern="^[a-fA-F0-9-]+$")
    feedback_type: str = Field(pattern="^(helpful|not_helpful|incorrect|too_detailed|too_brief|wrong_asset|wrong_timeframe|tool_failure|interpretation_error|missing_context)$")
    correction: str = Field(default="", max_length=500)
    comment: str = Field(default="", max_length=500)


class AssistantPreferenceCorrection(BaseModel):
    model_config = {"extra": "forbid"}
    preference_key: str = Field(pattern="^(response_detail|response_format)$")
    preference_value: str = Field(pattern="^(concise|detailed|structured|narrative)$")


@router.post("/feedback")
async def submit_assistant_feedback(request: Request, payload: AssistantFeedbackCreate):
    owner_key = _memory_owner(request)
    if payload.feedback_type == "too_detailed":
        preference_key, preference_value = "response_detail", "concise"
    elif payload.feedback_type == "too_brief":
        preference_key, preference_value = "response_detail", "detailed"
    else:
        preference_key = preference_value = None

    # Do not persist credential-like strings in optional user comments/corrections.
    secret_pattern = re.compile(r"(?i)(api[_ -]?key|password|token|secret)\\s*[:=]|\\bBearer\\s+")
    correction = payload.correction.strip()
    comment = payload.comment.strip()
    if secret_pattern.search(correction) or secret_pattern.search(comment):
        raise HTTPException(status_code=422, detail="Feedback cannot contain credentials or secrets.")

    repository = _memory_repository()
    feedback_id = uuid4().hex
    saved = repository.save_assistant_feedback({
        "feedback_id": feedback_id, "owner_key": owner_key,
        "request_id": payload.request_id.lower(), "feedback_type": payload.feedback_type,
        "correction": preference_key or correction[:500], "comment": comment[:500],
    })
    adapted = None
    threshold = 3
    if preference_key:
        evidence = repository.count_assistant_feedback(
            owner_key, payload.feedback_type, preference_key=preference_key,
        )
        # Repeated preference-specific feedback is required; isolated ratings never adapt.
        if evidence >= threshold:
            adapted = repository.set_assistant_preference(
                owner_key, preference_key, preference_value, source="feedback",
                evidence_count=evidence, confidence=min(0.85, 0.55 + 0.05 * evidence),
            )
    return {"status": "recorded", "feedback": saved, "adapted_preference": adapted,
            "adaptation_threshold": threshold}


@router.get("/preferences")
async def list_assistant_preferences(request: Request):
    owner_key = _memory_owner(request)
    return {"preferences": _memory_repository().get_assistant_preferences(owner_key)}


@router.put("/preferences")
async def correct_assistant_preference(request: Request, payload: AssistantPreferenceCorrection):
    owner_key = _memory_owner(request)
    key, value = payload.preference_key, payload.preference_value
    valid_values = {
        "response_detail": {"concise", "detailed"},
        "response_format": {"structured", "narrative"},
    }
    if value not in valid_values[key]:
        raise HTTPException(status_code=422, detail="Preference value is not valid for this preference.")
    preference = _memory_repository().set_assistant_preference(
        owner_key, key, value, source="user_correction", evidence_count=1, confidence=1.0,
    )
    return {"status": "corrected", "preference": preference}


@router.delete("/preferences/{preference_key}")
async def delete_assistant_preference(preference_key: str, request: Request):
    owner_key = _memory_owner(request)
    if preference_key not in {"response_detail", "response_format"}:
        raise HTTPException(status_code=404, detail="Preference not found")
    if not _memory_repository().delete_assistant_preference(owner_key, preference_key):
        raise HTTPException(status_code=404, detail="Preference not found")
    return {"status": "deleted", "preference_key": preference_key}


class MonitoringTaskCreate(BaseModel):
    model_config = {"extra": "forbid"}
    symbol: str = Field(min_length=2, max_length=32)
    market: str = Field(default="SPOT", pattern="^(SPOT|FUTURES)$")
    condition: str = Field(pattern="^(price_above|price_below)$")
    threshold: float = Field(gt=0, allow_inf_nan=False)
    ttl_seconds: int = Field(default=86400, ge=60, le=2592000)


def _realtime_service():
    bridge = get_bridge()
    service = getattr(bridge.orch, "realtime_intelligence", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Realtime intelligence is not running")
    return service


@router.post("/monitoring")
async def create_monitoring_task(request: Request, payload: MonitoringTaskCreate):
    owner_key = _memory_owner(request)
    try:
        task = _realtime_service().create_task(
            owner_key, payload.symbol, payload.market, payload.condition,
            payload.threshold, ttl_seconds=payload.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"task": task}


@router.get("/monitoring")
async def list_monitoring_tasks(request: Request):
    owner_key = _memory_owner(request)
    return {"tasks": _realtime_service().list_tasks(owner_key)}


@router.delete("/monitoring/{task_id}")
async def cancel_monitoring_task(task_id: str, request: Request):
    owner_key = _memory_owner(request)
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise HTTPException(status_code=404, detail="Monitoring task not found")
    if not _realtime_service().cancel_task(owner_key, task_id):
        raise HTTPException(status_code=404, detail="Monitoring task not found")
    return {"task_id": task_id, "status": "cancelled"}


@router.get("/monitoring/status")
async def realtime_intelligence_status(request: Request):
    _memory_owner(request)
    return _realtime_service().status_snapshot()
