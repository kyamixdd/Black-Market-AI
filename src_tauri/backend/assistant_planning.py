"""Bounded dependency-aware plans for assistant evidence requests."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from .assistant_tool_registry import AssistantToolRegistry, ToolRegistryError


class PlanStepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass
class PlanStep:
    step_id: str
    tool_id: str
    arguments: dict[str, Any]
    dependencies: tuple[str, ...] = ()
    state: PlanStepState = PlanStepState.PENDING
    attempts: int = 0
    result: dict[str, Any] | None = None
    error_code: str | None = None


@dataclass
class AssistantTaskPlan:
    task_id: str = field(default_factory=lambda: uuid4().hex)
    steps: list[PlanStep] = field(default_factory=list)
    max_steps: int = 8
    max_tool_calls: int = 8
    max_retries: int = 1

    def validate(self) -> None:
        if not self.steps or len(self.steps) > self.max_steps:
            raise ToolRegistryError("invalid_plan", "Task plan is empty or exceeds the step limit.")
        if len(self.steps) > self.max_tool_calls:
            raise ToolRegistryError("tool_budget_exceeded", "Task plan exceeds the tool-call budget.")
        known: set[str] = set()
        for step in self.steps:
            if not step.step_id or step.step_id in known:
                raise ToolRegistryError("invalid_plan", "Task plan contains duplicate or empty step identifiers.")
            if step.step_id in step.dependencies or set(step.dependencies) - known:
                raise ToolRegistryError("invalid_plan", "Task plan contains a missing or forward dependency.")
            known.add(step.step_id)


def build_plan(tool_ids: list[str], arguments: dict[str, Any], *, task_id: str | None = None) -> AssistantTaskPlan:
    """Build a bounded plan from validated intent tool identifiers."""
    unique_tools = list(dict.fromkeys(tool_ids))
    plan = AssistantTaskPlan(
        task_id=task_id or uuid4().hex,
        steps=[
            PlanStep(step_id=f"step-{index + 1}", tool_id=tool_id, arguments=dict(arguments))
            for index, tool_id in enumerate(unique_tools)
        ],
    )
    plan.validate()
    return plan


@dataclass
class PlanExecution:
    task_id: str
    state: str
    step_results: list[dict[str, Any]]
    completed_steps: list[str]
    failed_steps: list[str]
    blocked_steps: list[str]
    cancelled_steps: list[str]
    attempts: int
    trace: list[str]


class TaskExecutionManager:
    """In-process cancellation registry for currently executing assistant tasks."""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def register(self, task_id: str) -> asyncio.Event:
        event = self._events.get(task_id)
        if event is None:
            event = asyncio.Event()
            self._events[task_id] = event
        return event

    def cancel(self, task_id: str) -> bool:
        event = self._events.get(task_id)
        if event is None:
            return False
        event.set()
        return True

    def unregister(self, task_id: str) -> None:
        self._events.pop(task_id, None)


TASK_EXECUTION_MANAGER = TaskExecutionManager()

async def execute_plan(
    plan: AssistantTaskPlan,
    registry: AssistantToolRegistry,
    bridge: Any,
    *,
    cancel_event: asyncio.Event | None = None,
    permissions: set[str] | None = None,
) -> PlanExecution:
    """Execute ready steps sequentially with bounded read-only retries."""
    plan.validate()
    cancel_event = cancel_event or asyncio.Event()
    states = {step.step_id: step.state for step in plan.steps}
    results: list[dict[str, Any]] = []
    trace = ["received", "planning", "executing"]
    total_attempts = 0
    cancelled = False

    for step in plan.steps:
        if cancel_event.is_set():
            cancelled = True
            step.state = PlanStepState.CANCELLED
            states[step.step_id] = step.state
            continue
        if any(states[dependency] != PlanStepState.COMPLETED for dependency in step.dependencies):
            step.state = PlanStepState.BLOCKED
            states[step.step_id] = step.state
            continue

        step.state = PlanStepState.RUNNING
        last_error: ToolRegistryError | None = None
        for attempt in range(plan.max_retries + 1):
            if cancel_event.is_set():
                cancelled = True
                step.state = PlanStepState.CANCELLED
                break
            step.attempts += 1
            total_attempts += 1
            invocation = asyncio.create_task(registry.invoke(
                bridge, step.tool_id, step.arguments, permissions=permissions
            ))
            cancellation = asyncio.create_task(cancel_event.wait())
            done, _ = await asyncio.wait(
                {invocation, cancellation}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancellation in done and cancel_event.is_set():
                invocation.cancel()
                try:
                    await invocation
                except asyncio.CancelledError:
                    pass
                step.state = PlanStepState.CANCELLED
                cancelled = True
                cancellation.cancel()
                break
            cancellation.cancel()
            try:
                step.result = await invocation
                step.state = PlanStepState.COMPLETED
                break
            except ToolRegistryError as exc:
                last_error = exc
                # Registry currently exposes only read-only tools; retry only
                # transient execution/timeout failures, never validation/permission errors.
                if exc.code not in {"tool_timeout", "tool_execution_failed"} or attempt >= plan.max_retries:
                    step.state = PlanStepState.FAILED
                    step.error_code = exc.code
                    break
        states[step.step_id] = step.state
        results.append({
            "step_id": step.step_id,
            "tool_id": step.tool_id,
            "state": step.state.value,
            "attempts": step.attempts,
            "result": step.result,
            "error_code": step.error_code,
        })

    completed = [s.step_id for s in plan.steps if s.state == PlanStepState.COMPLETED]
    failed = [s.step_id for s in plan.steps if s.state == PlanStepState.FAILED]
    blocked = [s.step_id for s in plan.steps if s.state == PlanStepState.BLOCKED]
    cancelled_steps = [s.step_id for s in plan.steps if s.state == PlanStepState.CANCELLED]
    if cancelled or cancelled_steps:
        state = "cancelled" if not completed else "partially_completed"
        trace.append(state)
    elif failed or blocked:
        state = "partially_completed" if completed else "failed"
        trace.append(state)
    else:
        state = "completed"
        trace.extend(["validating", "completed"])
    return PlanExecution(
        task_id=plan.task_id,
        state=state,
        step_results=results,
        completed_steps=completed,
        failed_steps=failed,
        blocked_steps=blocked,
        cancelled_steps=cancelled_steps,
        attempts=total_attempts,
        trace=trace,
    )
