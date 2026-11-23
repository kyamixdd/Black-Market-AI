"""Tests for bounded dependency-aware assistant task execution."""
import asyncio

import pytest

from src_tauri.backend.assistant_planning import (
    AssistantTaskPlan,
    PlanStep,
    PlanStepState,
    build_plan,
    execute_plan,
)
from src_tauri.backend.assistant_tool_registry import ToolRegistryError


class FakeRegistry:
    def __init__(self, failures=None):
        self.failures = dict(failures or {})
        self.calls = []

    async def invoke(self, bridge, tool_id, arguments, *, permissions=None):
        self.calls.append(tool_id)
        remaining = self.failures.get(tool_id, 0)
        if remaining:
            self.failures[tool_id] = remaining - 1
            raise ToolRegistryError("tool_execution_failed", "temporary")
        return {"tool": tool_id, "status": "available", "data": {}, "source": "test"}


def test_plan_deduplicates_tools_and_respects_budget():
    plan = build_plan(["market_snapshot", "risk_status", "market_snapshot"], {"symbol": "BTCUSDT"})
    assert [step.tool_id for step in plan.steps] == ["market_snapshot", "risk_status"]
    assert plan.task_id


def test_plan_rejects_forward_or_unknown_dependency():
    plan = AssistantTaskPlan(steps=[
        PlanStep("first", "market_snapshot", {}, dependencies=("second",)),
        PlanStep("second", "risk_status", {}),
    ])
    with pytest.raises(ToolRegistryError) as error:
        plan.validate()
    assert error.value.code == "invalid_plan"


@pytest.mark.asyncio
async def test_dependencies_block_after_failed_prerequisite():
    registry = FakeRegistry({"market_snapshot": 3})
    plan = AssistantTaskPlan(max_retries=0, steps=[
        PlanStep("snapshot", "market_snapshot", {}),
        PlanStep("risk", "risk_status", {}, dependencies=("snapshot",)),
    ])
    result = await execute_plan(plan, registry, object())
    assert result.state == "failed"
    assert result.failed_steps == ["snapshot"]
    assert result.blocked_steps == ["risk"]
    assert registry.calls == ["market_snapshot"]


@pytest.mark.asyncio
async def test_transient_read_only_failure_retries_once():
    registry = FakeRegistry({"market_snapshot": 1})
    plan = build_plan(["market_snapshot"], {})
    result = await execute_plan(plan, registry, object())
    assert result.state == "completed"
    assert result.attempts == 2
    assert registry.calls == ["market_snapshot", "market_snapshot"]


@pytest.mark.asyncio
async def test_non_retryable_validation_failure_does_not_retry():
    class InvalidRegistry:
        def __init__(self):
            self.calls = 0

        async def invoke(self, *args, **kwargs):
            self.calls += 1
            raise ToolRegistryError("invalid_arguments", "invalid")

    registry = InvalidRegistry()
    result = await execute_plan(build_plan(["market_snapshot"], {}), registry, object())
    assert result.state == "failed"
    assert result.attempts == 1
    assert registry.calls == 1


@pytest.mark.asyncio
async def test_partial_completion_preserves_success_and_reports_failure():
    registry = FakeRegistry({"risk_status": 3})
    plan = build_plan(["market_snapshot", "risk_status"], {})
    result = await execute_plan(plan, registry, object())
    assert result.state == "partially_completed"
    assert result.completed_steps == ["step-1"]
    assert result.failed_steps == ["step-2"]
    assert result.step_results[0]["result"]["tool"] == "market_snapshot"


@pytest.mark.asyncio
async def test_cancel_event_stops_pending_steps():
    registry = FakeRegistry()
    event = asyncio.Event()
    event.set()
    result = await execute_plan(build_plan(["market_snapshot", "risk_status"], {}), registry, object(), cancel_event=event)
    assert result.state == "cancelled"
    assert result.cancelled_steps == ["step-1", "step-2"]
    assert registry.calls == []


@pytest.mark.asyncio
async def test_cancel_interrupts_inflight_tool():
    class SlowRegistry:
        async def invoke(self, *args, **kwargs):
            await asyncio.sleep(1)
            return {"tool": "market_snapshot", "status": "available", "data": {}, "source": "test"}

    event = asyncio.Event()
    plan = build_plan(["market_snapshot"], {})
    task = asyncio.create_task(execute_plan(plan, SlowRegistry(), object(), cancel_event=event))
    await asyncio.sleep(0.02)
    event.set()
    result = await asyncio.wait_for(task, timeout=0.2)
    assert result.state == "cancelled"
    assert result.cancelled_steps == ["step-1"]
