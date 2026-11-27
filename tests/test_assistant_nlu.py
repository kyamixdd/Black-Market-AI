"""Regression tests for structured assistant language understanding."""
import pytest

from src_tauri.backend.assistant_nlu import (
    ConfidenceLevel,
    ContextSnapshot,
    parse_assistant_request,
)


def test_extracts_market_intent_symbol_and_timeframe():
    parsed = parse_assistant_request("Analyze BTC on the 15m timeframe")
    assert parsed.intents[0].tool == "market_snapshot"
    assert parsed.entities["symbol"] == "BTCUSDT"
    assert parsed.entities["timeframe"] == "15m"
    assert parsed.confidence == ConfidenceLevel.HIGH
    assert not parsed.clarification_required


def test_detects_multiple_intents_and_parameters():
    parsed = parse_assistant_request(
        "Show BTC indicators and risk status over the last 90 days, exclude stale"
    )
    assert {intent.tool for intent in parsed.intents} == {"indicator_report", "risk_status"}
    assert parsed.entities["durations"] == [{"value": 90, "unit": "day"}]
    assert "exclude stale" in parsed.constraints
    assert parsed.confidence == ConfidenceLevel.MEDIUM


def test_resolves_contextual_reference_only_with_context():
    parsed = parse_assistant_request(
        "Compare it using the same timeframe",
        context=ContextSnapshot(symbol="ETHUSDT", timeframe="4h", previous_query="ETH analysis"),
    )
    assert parsed.parameters["symbol"] == "ETHUSDT"
    assert parsed.parameters["timeframe"] == "4h"
    assert "it" in parsed.context_references
    assert not parsed.clarification_required


def test_asks_for_missing_reference_context():
    parsed = parse_assistant_request("Analyze it again")
    assert parsed.clarification_required
    assert parsed.clarification_question == "Which asset are you referring to?"
    assert parsed.confidence == ConfidenceLevel.LOW
    assert parsed.intents == ()
    assert not parsed.unsupported


def test_disambiguates_compound_intent_phrases():
    scanner = parse_assistant_request("Check the market scanner")
    assert [intent.tool for intent in scanner.intents] == ["scanner_status"]

    trades = parse_assistant_request("Show recent trade history")
    assert [intent.tool for intent in trades.intents] == ["trade_history"]

    risk = parse_assistant_request("What is my portfolio risk exposure")
    assert [intent.tool for intent in risk.intents] == ["risk_status"]


def test_unsupported_request_is_not_routed_to_snapshot():
    parsed = parse_assistant_request("Remember that I prefer detailed explanations")
    assert parsed.unsupported
    assert not parsed.intents
    assert parsed.clarification_required


def test_rejects_invalid_timeframe_and_symbol():
    with pytest.raises(ValueError):
        parse_assistant_request("Analyze BTC", timeframe="2h")
    with pytest.raises(ValueError):
        parse_assistant_request("Analyze market", symbol="BTC/USDT")


def test_extracts_multiple_assets_for_comparison():
    parsed = parse_assistant_request("Compare BTC with ETH")
    assert parsed.entities["assets"] == ["BTCUSDT", "ETHUSDT"]
    assert parsed.confidence == ConfidenceLevel.MEDIUM


def test_parses_natural_language_timeframe():
    parsed = parse_assistant_request("Analyze BTC on the 15-minute timeframe")
    assert parsed.entities["timeframe"] == "15m"
