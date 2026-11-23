"""Tests for the bounded Stage 1 assistant orchestration boundary."""
import pytest

from src_tauri.backend.assistant_runtime import (
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

    assert trace.transitions == [
        "received", "interpreting", "executing", "validating", "completed"
    ]
    with pytest.raises(ValueError):
        trace.transition(AssistantTaskState.FAILED)


@pytest.mark.asyncio
async def test_runtime_returns_trace_and_evidence_only():
    class Bridge:
        def get_market_snapshot(self, symbol, market):
            return {
                "symbol": symbol,
                "market": market,
                "price": 123.0,
                "price_change_24h": 1.2,
                "regime": "UNKNOWN",
                "data_freshness": "DELAYED",
                "data_age_seconds": 120,
            }

    result = await execute_assistant_query(
        Bridge(), "show current market snapshot", "BTCUSDT", "SPOT", "1h"
    )

    assert result.task_state == "completed"
    assert result.task_trace == (
        "received", "interpreting", "executing", "validating", "completed"
    )
    assert result.tool == "market_snapshot"
    assert result.status == "available"
    assert "123.0" in result.answer
    assert result.sources == ("local backend",)


@pytest.mark.asyncio
async def test_runtime_marks_failure_when_tool_rejects_input():
    with pytest.raises(ValueError):
        await execute_assistant_query(
            object(), "show current market snapshot", "BTC/USDT", "SPOT", "1h"
        )
