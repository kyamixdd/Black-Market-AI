"""Tests for the bounded Stage 1/2 assistant orchestration boundary."""
import pytest

from src_tauri.backend.assistant_runtime import (
    AssistantRuntimeError,
    AssistantTaskState,
    AssistantTaskTrace,
    execute_assistant_query,
)


def test_task_trace_enforces_terminal_state():
    trace = AssistantTaskTrace()
    trace.transition(AssistantTaskState.INTERPRETING)
    trace.transition(AssistantTaskState.EXECUTING)
    trace.transition(AssistantTaskState.VALIDATING)
    trace.transition(AssistantTaskState.COMPLETED)
    assert trace.transitions == ["received", "interpreting", "executing", "validating", "completed"]
    with pytest.raises(ValueError):
        trace.transition(AssistantTaskState.FAILED)


@pytest.mark.asyncio
async def test_runtime_returns_trace_and_evidence_only(monkeypatch):
    monkeypatch.setenv("BLACKMARKET_ASSISTANT_PROVIDER", "disabled")

    class Bridge:
        def get_market_snapshot(self, symbol, market):
            return {
                "symbol": symbol, "market": market, "price": 123.0,
                "price_change_24h": 1.2, "regime": "UNKNOWN",
                "data_freshness": "DELAYED", "data_age_seconds": 120,
            }

    result = await execute_assistant_query(
        Bridge(), "show current market snapshot", "BTCUSDT", "SPOT", "1h"
    )
    assert result.task_state == "completed"
    assert result.task_trace == ("received", "interpreting", "executing", "validating", "completed")
    assert result.tool == "market_snapshot"
    assert result.status == "available"
    assert "123.0" in result.answer
    assert result.sources == ("local backend",)
    assert result.structured_request.entities["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_runtime_executes_distinct_supported_intents():
    class Bridge:
        def get_market_snapshot(self, symbol, market):
            return {"symbol": symbol, "market": market, "price": 50, "price_change_24h": 0, "regime": "UNKNOWN", "data_freshness": "FRESH", "data_age_seconds": 0}
        def get_risk_metrics(self):
            return {"exposure": 0, "risk_status": "within_limits"}

    result = await execute_assistant_query(
        Bridge(), "show market snapshot and risk status", "BTCUSDT", "SPOT", "1h"
    )
    assert result.task_state == "completed"
    assert result.status == "available"
    assert isinstance(result.data, list)
    assert len(result.data) == 2
    assert "risk_status" in result.answer


@pytest.mark.asyncio
async def test_runtime_asks_before_multi_asset_comparison():
    result = await execute_assistant_query(
        object(), "Compare BTC with ETH", "BTCUSDT", "SPOT", "1h"
    )
    assert result.task_state == "awaiting_clarification"
    assert result.status == "clarification_required"
    assert "one asset at a time" in result.answer


@pytest.mark.asyncio
async def test_runtime_failure_contains_failed_task_trace():
    with pytest.raises(AssistantRuntimeError) as error:
        await execute_assistant_query(
            object(), "show current market snapshot", "BTC/USDT", "SPOT", "1h"
        )
    assert error.value.status_code == 422
    assert error.value.task_state == "failed"
    assert error.value.task_trace == ("received", "interpreting", "failed")


@pytest.mark.asyncio
async def test_runtime_reports_partial_completion_when_one_tool_fails(monkeypatch):
    monkeypatch.setenv("BLACKMARKET_ASSISTANT_PROVIDER", "disabled")

    class Registry:
        async def invoke(self, bridge, tool_id, arguments, *, permissions=None):
            if tool_id == "risk_status":
                from src_tauri.backend.assistant_tool_registry import ToolRegistryError
                raise ToolRegistryError("invalid_arguments", "bad input")
            return {"tool": tool_id, "status": "available", "data": {"price": 12}, "source": "test"}

    monkeypatch.setattr(
        "src_tauri.backend.assistant_runtime.create_default_registry",
        lambda: Registry(),
    )
    result = await execute_assistant_query(
        object(), "show market snapshot and risk status", "BTCUSDT", "SPOT", "1h"
    )
    assert result.task_state == "partially_completed"
    assert result.status == "partial"
    assert "Task partially completed" in result.answer
    assert "market_snapshot" in result.answer
