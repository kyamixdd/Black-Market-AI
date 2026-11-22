"""Tests for the evidence-grounded assistant tool registry."""
import pytest

from src_tauri.backend.assistant_intelligence import execute_tool, select_tool, validate_market, validate_symbol

def test_tool_selection_is_allowlisted_and_intent_based():
    assert select_tool("show current market regime") == "market_snapshot"
    assert select_tool("show indicators and ATR") == "indicator_report"
    assert select_tool("what is my paper account equity") == "paper_account"
    assert select_tool("show scanner status") == "scanner_status"

def test_input_validation_rejects_invalid_market_and_symbol():
    with pytest.raises(ValueError): validate_symbol("BTC/USDT")
    with pytest.raises(ValueError): validate_market("MARGIN")

@pytest.mark.asyncio
async def test_missing_market_data_is_reported_as_unavailable():
    class Bridge:
        def get_market_snapshot(self, symbol, market): return None
    result = await execute_tool(Bridge(), "market_snapshot", "BTCUSDT", "SPOT")
    assert result["status"] == "unavailable"
    assert result["data"] is None

@pytest.mark.asyncio
async def test_unsupported_tool_is_rejected():
    with pytest.raises(ValueError):
        await execute_tool(object(), "arbitrary_code", "BTCUSDT", "SPOT")
