"""Bounded request orchestration for deterministic assistant evidence tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .assistant_intelligence import (
    optional_provider_interpretation,
    summarize_result,
    validate_market,
    validate_symbol,
)
from .assistant_nlu import ContextSnapshot, StructuredAssistantRequest, parse_assistant_request
from .assistant_tool_registry import ToolRegistryError, create_default_registry


class AssistantTaskState(str, Enum):
    RECEIVED = "received"
    INTERPRETING = "interpreting"
    AWAITING_CLARIFICATION = "awaiting_clarification"
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
            AssistantTaskState.INTERPRETING: {AssistantTaskState.AWAITING_CLARIFICATION, AssistantTaskState.EXECUTING, AssistantTaskState.FAILED},
            AssistantTaskState.AWAITING_CLARIFICATION: set(),
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

    def __init__(self, message: str, trace: AssistantTaskTrace, status_code: int, error_code: str = "assistant_request_failed"):
        super().__init__(message)
        self.task_id = trace.task_id
        self.task_state = trace.state.value
        self.task_trace = tuple(trace.transitions)
        self.status_code = status_code
        self.error_code = error_code


@dataclass(frozen=True)
class AssistantExecution:
    task_id: str
    task_state: str
    task_trace: tuple[str, ...]
    answer: str
    tool: str | None
    status: str
    data: Any
    sources: tuple[str, ...]
    interpretation: str | None = None
    structured_request: StructuredAssistantRequest | None = None


async def execute_assistant_query(
    bridge: Any,
    query: str,
    symbol: str = "BTCUSDT",
    market: str = "SPOT",
    timeframe: str = "1h",
    context: ContextSnapshot | None = None,
) -> AssistantExecution:
    """Interpret and execute up to three distinct evidence intents."""
    trace = AssistantTaskTrace()
    try:
        trace.transition(AssistantTaskState.INTERPRETING)
        parsed = parse_assistant_request(
            query, symbol=validate_symbol(symbol), market=validate_market(market),
            timeframe=timeframe, context=context, request_id=trace.task_id,
        )
        tools = list(dict.fromkeys(intent.tool for intent in parsed.intents))
        assets = parsed.entities.get("assets", [])

        # Current evidence tools accept one asset at a time; do not imply a comparison.
        if len(assets) > 1:
            parsed_question = "I identified " + " and ".join(assets) + ", but the current assistant tools retrieve one asset per request. Please ask for one asset at a time."
            trace.transition(AssistantTaskState.AWAITING_CLARIFICATION)
            return AssistantExecution(
                task_id=trace.task_id, task_state=trace.state.value,
                task_trace=tuple(trace.transitions), answer=parsed_question,
                tool=None, status="clarification_required", data=None, sources=(),
                structured_request=parsed,
            )
        if parsed.clarification_required or parsed.unsupported:
            trace.transition(AssistantTaskState.AWAITING_CLARIFICATION)
            return AssistantExecution(
                task_id=trace.task_id, task_state=trace.state.value,
                task_trace=tuple(trace.transitions),
                answer=parsed.clarification_question or "Please clarify the request.",
                tool=None, status="clarification_required", data=None, sources=(),
                structured_request=parsed,
            )
        if not tools:
            raise ValueError("No supported assistant tool was identified.")
        if len(tools) > 3:
            trace.transition(AssistantTaskState.AWAITING_CLARIFICATION)
            return AssistantExecution(
                task_id=trace.task_id, task_state=trace.state.value,
                task_trace=tuple(trace.transitions),
                answer="This request contains more than three evidence categories. Please split it into smaller requests.",
                tool=None, status="clarification_required", data=None, sources=(),
                structured_request=parsed,
            )

        trace.transition(AssistantTaskState.EXECUTING)
        results = []
        registry = create_default_registry()
        arguments = {
            "symbol": parsed.parameters["symbol"],
            "market": parsed.parameters["market"],
            "timeframe": parsed.parameters["timeframe"],
        }
        for tool in tools:
            results.append(await registry.invoke(bridge, tool, arguments))

        trace.transition(AssistantTaskState.VALIDATING)
        summaries = [summarize_result(query, item) for item in results]
        answer = summaries[0] if len(summaries) == 1 else "\n\n".join(
            f"{item.get('tool', 'evidence')}: {summary}"
            for item, summary in zip(results, summaries)
        )
        interpretation = None
        if len(results) == 1:
            interpretation = await optional_provider_interpretation(query, results[0])
            if interpretation:
                answer += "\n\nOptional provider interpretation (not verified facts): " + interpretation

        trace.transition(AssistantTaskState.COMPLETED)
        primary = results[0]
        return AssistantExecution(
            task_id=trace.task_id, task_state=trace.state.value,
            task_trace=tuple(trace.transitions), answer=answer,
            tool=primary.get("tool"), status="available" if all(r.get("status") == "available" for r in results) else "partial",
            data=primary.get("data") if len(results) == 1 else [r.get("data") for r in results],
            sources=tuple(dict.fromkeys(r.get("source", "local backend") for r in results)),
            interpretation=interpretation, structured_request=parsed,
        )
    except ToolRegistryError as exc:
        if trace.state not in {AssistantTaskState.COMPLETED, AssistantTaskState.FAILED, AssistantTaskState.AWAITING_CLARIFICATION}:
            trace.transition(AssistantTaskState.FAILED)
        raise AssistantRuntimeError(str(exc), trace, exc.status_code, exc.code) from exc
    except ValueError as exc:
        if trace.state not in {AssistantTaskState.COMPLETED, AssistantTaskState.FAILED, AssistantTaskState.AWAITING_CLARIFICATION}:
            trace.transition(AssistantTaskState.FAILED)
        raise AssistantRuntimeError(str(exc), trace, 422) from exc
    except Exception as exc:
        if trace.state not in {AssistantTaskState.COMPLETED, AssistantTaskState.FAILED, AssistantTaskState.AWAITING_CLARIFICATION}:
            trace.transition(AssistantTaskState.FAILED)
        raise AssistantRuntimeError(
            "Assistant request failed while retrieving or validating local evidence.",
            trace, 500,
        ) from exc
