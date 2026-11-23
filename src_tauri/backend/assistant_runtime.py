"""Request orchestration boundary for the deterministic market assistant."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .assistant_intelligence import (
    execute_tool,
    optional_provider_interpretation,
    select_tool,
    summarize_result,
    validate_market,
    validate_symbol,
)


class AssistantTaskState(str, Enum):
    RECEIVED = "received"
    INTERPRETING = "interpreting"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AssistantTaskTrace:
    """Bounded in-request lifecycle trace; not a persistent task store."""

    task_id: str = field(default_factory=lambda: uuid4().hex)
    state: AssistantTaskState = AssistantTaskState.RECEIVED
    transitions: list[str] = field(default_factory=lambda: [AssistantTaskState.RECEIVED.value])

    def transition(self, next_state: AssistantTaskState) -> None:
        allowed = {
            AssistantTaskState.RECEIVED: {AssistantTaskState.INTERPRETING, AssistantTaskState.FAILED},
            AssistantTaskState.INTERPRETING: {AssistantTaskState.EXECUTING, AssistantTaskState.FAILED},
            AssistantTaskState.EXECUTING: {AssistantTaskState.VALIDATING, AssistantTaskState.FAILED},
            AssistantTaskState.VALIDATING: {AssistantTaskState.COMPLETED, AssistantTaskState.FAILED},
            AssistantTaskState.COMPLETED: set(),
            AssistantTaskState.FAILED: set(),
        }
        if next_state not in allowed[self.state]:
            raise ValueError(f"Invalid assistant task transition: {self.state} -> {next_state}")
        self.state = next_state
        self.transitions.append(next_state.value)


class AssistantRuntimeError(Exception):
    """Safe API-facing failure carrying the bounded request lifecycle."""

    def __init__(self, message: str, trace: AssistantTaskTrace, status_code: int):
        super().__init__(message)
        self.task_id = trace.task_id
        self.task_state = trace.state.value
        self.task_trace = tuple(trace.transitions)
        self.status_code = status_code


@dataclass(frozen=True)
class AssistantExecution:
    """Validated assistant response and its execution metadata."""

    task_id: str
    task_state: str
    task_trace: tuple[str, ...]
    answer: str
    tool: str | None
    status: str
    data: Any
    sources: tuple[str, ...]
    interpretation: str | None = None


async def execute_assistant_query(
    bridge: Any,
    query: str,
    symbol: str = "BTCUSDT",
    market: str = "SPOT",
    timeframe: str = "1h",
) -> AssistantExecution:
    """Run one bounded assistant request through existing evidence services."""
    trace = AssistantTaskTrace()
    try:
        trace.transition(AssistantTaskState.INTERPRETING)
        normalized_symbol = validate_symbol(symbol)
        normalized_market = validate_market(market)
        tool = select_tool(query)

        trace.transition(AssistantTaskState.EXECUTING)
        evidence = await execute_tool(
            bridge, tool, normalized_symbol, normalized_market, timeframe
        )

        trace.transition(AssistantTaskState.VALIDATING)
        answer = summarize_result(query, evidence)
        interpretation = await optional_provider_interpretation(query, evidence)
        if interpretation:
            answer += "\\n\\nOptional provider interpretation (not verified facts): " + interpretation

        trace.transition(AssistantTaskState.COMPLETED)
        return AssistantExecution(
            task_id=trace.task_id,
            task_state=trace.state.value,
            task_trace=tuple(trace.transitions),
            answer=answer,
            tool=evidence.get("tool"),
            status=evidence.get("status", "unavailable"),
            data=evidence.get("data"),
            sources=(evidence.get("source", "local backend"),),
            interpretation=interpretation,
        )
    except ValueError as exc:
        if trace.state not in {AssistantTaskState.COMPLETED, AssistantTaskState.FAILED}:
            trace.transition(AssistantTaskState.FAILED)
        raise AssistantRuntimeError(str(exc), trace, 422) from exc
    except Exception as exc:
        if trace.state not in {AssistantTaskState.COMPLETED, AssistantTaskState.FAILED}:
            trace.transition(AssistantTaskState.FAILED)
        raise AssistantRuntimeError(
            "Assistant request failed while retrieving or validating local evidence.",
            trace,
            500,
        ) from exc
