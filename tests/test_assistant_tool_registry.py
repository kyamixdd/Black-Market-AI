"""Unit tests for the controlled assistant tool registry."""
import asyncio

import pytest

from src_tauri.backend.assistant_tool_registry import (
    AssistantToolRegistry,
    ToolRegistryError,
    ToolSpec,
)


def spec(**overrides):
    values = dict(
        tool_id="market_snapshot",
        description="Read a current market snapshot",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "market": {"type": "string"},
                "timeframe": {"type": "string"},
            },
            "required": ["symbol", "market", "timeframe"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        required_permissions=frozenset({"market:read"}),
        timeout_seconds=0.2,
        read_only=True,
        changes_state=False,
    )
    values.update(overrides)
    return ToolSpec(**values)


@pytest.mark.asyncio
async def test_registered_tool_executes_and_returns_trace_metadata():
    async def executor(bridge, tool, symbol, market, timeframe):
        assert bridge == "bridge"
        return {
            "tool": tool, "status": "available", "data": {"price": 1},
            "source": "test",
        }

    registry = AssistantToolRegistry(executor=executor, specs={"market_snapshot": spec()})
    result = await registry.invoke(
        "bridge", "market_snapshot",
        {"symbol": "btcusdt", "market": "SPOT", "timeframe": "15m"},
    )
    assert result["data"] == {"price": 1}
    assert result["execution"]["tool_id"] == "market_snapshot"
    assert result["execution"]["read_only"] is True
    assert result["execution"]["changes_state"] is False
    assert result["execution"]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected_before_executor():
    called = False

    async def executor(*args):
        nonlocal called
        called = True

    registry = AssistantToolRegistry(executor=executor, specs={"market_snapshot": spec()})
    with pytest.raises(ToolRegistryError) as error:
        await registry.invoke("bridge", "arbitrary_python", {})
    assert error.value.code == "unknown_tool"
    assert called is False


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments,code", [
    ({"symbol": "BTCUSDT", "market": "SPOT"}, "missing_parameters"),
    ({"symbol": "BTC/USDT", "market": "SPOT", "timeframe": "1h"}, "invalid_symbol"),
    ({"symbol": "BTCUSDT", "market": "LIVE", "timeframe": "1h"}, "invalid_market"),
    ({"symbol": "BTCUSDT", "market": "SPOT", "timeframe": "10m"}, "invalid_timeframe"),
    ({"symbol": "BTCUSDT", "market": "SPOT", "timeframe": "1h", "shell": "ls"}, "invalid_arguments"),
])
async def test_invalid_input_is_rejected(arguments, code):
    registry = AssistantToolRegistry(specs={"market_snapshot": spec()})
    with pytest.raises(ToolRegistryError) as error:
        await registry.invoke("bridge", "market_snapshot", arguments)
    assert error.value.code == code


@pytest.mark.asyncio
async def test_permissions_are_enforced():
    registry = AssistantToolRegistry(specs={"market_snapshot": spec()})
    with pytest.raises(ToolRegistryError) as error:
        await registry.invoke(
            "bridge", "market_snapshot",
            {"symbol": "BTCUSDT", "market": "SPOT", "timeframe": "1h"},
            permissions={"paper:read"},
        )
    assert error.value.status_code == 403
    assert error.value.code == "permission_denied"


@pytest.mark.asyncio
async def test_state_changing_tools_are_rejected():
    registry = AssistantToolRegistry(specs={
        "market_snapshot": spec(read_only=False, changes_state=True)
    })
    with pytest.raises(ToolRegistryError) as error:
        await registry.invoke(
            "bridge", "market_snapshot",
            {"symbol": "BTCUSDT", "market": "SPOT", "timeframe": "1h"},
        )
    assert error.value.code == "unsafe_tool"


@pytest.mark.asyncio
async def test_timeout_is_bounded():
    async def slow(*args):
        await asyncio.sleep(0.5)
        return {"tool": "market_snapshot", "status": "available", "data": {}, "source": "test"}

    registry = AssistantToolRegistry(
        executor=slow, specs={"market_snapshot": spec(timeout_seconds=0.01)}
    )
    with pytest.raises(ToolRegistryError) as error:
        await registry.invoke(
            "bridge", "market_snapshot",
            {"symbol": "BTCUSDT", "market": "SPOT", "timeframe": "1h"},
        )
    assert error.value.code == "tool_timeout"
    assert error.value.status_code == 504


@pytest.mark.asyncio
async def test_malformed_executor_result_is_rejected():
    async def bad(*args):
        return {"tool": "other", "status": "done"}

    registry = AssistantToolRegistry(executor=bad, specs={"market_snapshot": spec()})
    with pytest.raises(ToolRegistryError) as error:
        await registry.invoke(
            "bridge", "market_snapshot",
            {"symbol": "BTCUSDT", "market": "SPOT", "timeframe": "1h"},
        )
    assert error.value.code == "invalid_tool_result


def test_registry_metadata_is_explicit_and_read_only():
    registry = AssistantToolRegistry()
    tools = registry.list_tools()
    assert len(tools) == 11
    assert all(tool["read_only"] and not tool["changes_state"] for tool in tools)
    assert all(tool["input_schema"]["additionalProperties"] is False for tool in tools)
