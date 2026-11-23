"""Deterministic natural-language request parsing for supported assistant workflows.

This parser extracts structured signals without making market claims. It is
intentionally conservative: unsupported or ambiguous requests are represented
explicitly rather than silently routed to an unrelated tool.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .assistant_intelligence import select_tool, validate_market, validate_symbol

TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}
_TIMEFRAME_RE = re.compile(r"\b(1m|3m|5m|15m|30m|1h|4h|1d|1w)\b", re.I)
_SYMBOL_RE = re.compile(r"\b([A-Z0-9]{2,12}(?:USDT|USDC|USD|BTC|ETH)?)\b")
_DURATION_RE = re.compile(r"\b(?:last|past|over|for)\s+(\d+)\s+(minute|hour|day|week|month|year)s?\b", re.I)
_NUMBER_RE = re.compile(r"(?<![A-Z])\b\d+(?:\.\d+)?%?\b", re.I)


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class ContextSnapshot:
    """Only explicitly supplied, relevant conversation context."""

    symbol: str | None = None
    timeframe: str | None = None
    previous_query: str | None = None
    previous_tool: str | None = None


@dataclass(frozen=True)
class ParsedIntent:
    name: str
    tool: str | None
    evidence_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuredAssistantRequest:
    request_id: str
    original_text: str
    normalized_text: str
    intents: tuple[ParsedIntent, ...]
    entities: dict[str, Any]
    parameters: dict[str, Any]
    constraints: tuple[str, ...]
    context_references: tuple[str, ...]
    confidence: ConfidenceLevel
    confidence_reasons: tuple[str, ...]
    clarification_required: bool
    clarification_question: str | None
    unsupported: bool = False


def _intent_matches(text: str) -> list[ParsedIntent]:
    groups = [
        ("historical_data", "historical_candles", ("historical", "history", "candles", "ohlc")),
        ("indicators", "indicator_report", ("indicator", "sma", "ema", "atr", "volatility", "analytics")),
        ("scanner", "scanner_status", ("scanner", "scan status")),
        ("signals", "signal_report", ("signal", "signals", "rejected signal")),
        ("strategy", "strategy_report", ("strategy", "backtest", "weights")),
        ("positions", "open_positions", ("position", "open trade", "open trades")),
        ("trade_history", "trade_history", ("trade history", "closed trade", "recent trade")),
        ("risk", "risk_status", ("risk", "exposure", "risk limit")),
        ("learning", "learning_evaluation", ("learning", "model evaluation", "accuracy", "prediction")),
        ("paper_account", "paper_account", ("paper account", "equity", "balance", "pnl", "portfolio")),
        ("market_snapshot", "market_snapshot", ("market", "price", "regime", "analyze", "analyse", "compare")),
    ]
    matches: list[ParsedIntent] = []
    for name, tool, terms in groups:
        found = tuple(term for term in terms if term in text)
        if found:
            matches.append(ParsedIntent(name=name, tool=tool, evidence_terms=found))
    # Keep intent order aligned with first evidence occurrence, with a stable tie-break.
    positions = {intent.name: min(text.find(term) for term in intent.evidence_terms) for intent in matches}
    return sorted(matches, key=lambda intent: positions[intent.name])


def parse_assistant_request(
    text: str,
    *,
    symbol: str = "BTCUSDT",
    market: str = "SPOT",
    timeframe: str = "1h",
    context: ContextSnapshot | None = None,
    request_id: str | None = None,
) -> StructuredAssistantRequest:
    """Parse supported intent, entities, constraints, and context references."""
    from uuid import uuid4

    if not isinstance(text, str) or not text.strip():
        raise ValueError("Assistant query must not be empty.")
    original = text.strip()
    normalized = re.sub(r"\s+", " ", original).lower()
    safe_symbol = validate_symbol(symbol)
    safe_market = validate_market(market)
    safe_timeframe = timeframe.strip().lower()
    if safe_timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported timeframe.")

    context = context or ContextSnapshot()
    intent_matches = _intent_matches(normalized)
    if not intent_matches:
        selected = select_tool(normalized)
        # Existing selector's fallback is a snapshot only for clearly market-related asks.
        if any(word in normalized for word in ("market", "price", "btc", "eth", "crypto", "coin")):
            intent_matches = [ParsedIntent("market_snapshot", selected, ("market query",))]
        else:
            return StructuredAssistantRequest(
                request_id=request_id or uuid4().hex,
                original_text=original,
                normalized_text=normalized,
                intents=(),
                entities={},
                parameters={"symbol": safe_symbol, "market": safe_market, "timeframe": safe_timeframe},
                constraints=(),
                context_references=(),
                confidence=ConfidenceLevel.LOW,
                confidence_reasons=("No supported intent phrase was identified.",),
                clarification_required=True,
                clarification_question="What market or application information should I retrieve?",
                unsupported=True,
            )

    explicit_symbol = None
    # Detect common crypto symbols only when they are explicit in the user text.
    symbol_candidates = [m.group(1) for m in _SYMBOL_RE.finditer(original) if m.group(1).upper() not in {"I", "IT", "THE", "AND", "OR", "US", "USD", "BTC", "ETH"}]
    # Recognize common base tickers even when they are not quoted as a pair.
    common = re.search(r"\b(BTC|ETH|SOL|BNB|XRP|ADA|DOGE|AVAX|DOT|LINK|LTC|TRX)\b", original, re.I)
    if common:
        explicit_symbol = common.group(1).upper() + ("USDT" if not common.group(1).upper().endswith(("USDT", "USDC", "USD")) else "")
    elif symbol_candidates:
        candidate = symbol_candidates[0].upper()
        try:
            explicit_symbol = validate_symbol(candidate)
        except ValueError:
            explicit_symbol = None

    timeframe_match = _TIMEFRAME_RE.search(normalized)
    explicit_timeframe = timeframe_match.group(1).lower() if timeframe_match else None
    references = tuple(ref for ref in ("it", "that asset", "same timeframe", "previous", "earlier", "last result", "continue", "again") if re.search(r"\b" + re.escape(ref) + r"\b", normalized))
    resolved_symbol = explicit_symbol or (context.symbol if context and references else None) or safe_symbol
    resolved_timeframe = explicit_timeframe or (context.timeframe if context and references else None) or safe_timeframe

    durations = [
        {"value": int(m.group(1)), "unit": m.group(2).lower()}
        for m in _DURATION_RE.finditer(normalized)
    ]
    numbers = [m.group(0) for m in _NUMBER_RE.finditer(normalized)]
    constraints = tuple(
        phrase for phrase in ("exclude low-volume", "without low-volume", "only completed", "paper trading only", "exclude stale")
        if phrase in normalized
    )
    clarification = None
    needs_clarification = False
    if references and not explicit_symbol and not (context and context.symbol):
        needs_clarification = True
        clarification = "Which asset are you referring to?"
    if "same timeframe" in references and not explicit_timeframe and not (context and context.timeframe):
        needs_clarification = True
        clarification = "Which timeframe should I reuse?"

    reasons = ["Intent terms matched deterministic supported vocabulary."]
    confidence = ConfidenceLevel.HIGH
    if len(intent_matches) > 1:
        confidence = ConfidenceLevel.MEDIUM
        reasons.append("Multiple intents detected; current runtime executes one evidence tool per request.")
    if references and not (context and (context.symbol or context.timeframe)):
        confidence = ConfidenceLevel.LOW
        reasons.append("A conversational reference lacks a usable context value.")
    if not explicit_symbol:
        reasons.append("Asset uses the request's validated symbol parameter.")
    return StructuredAssistantRequest(
        request_id=request_id or uuid4().hex,
        original_text=original,
        normalized_text=normalized,
        intents=tuple(intent_matches),
        entities={
            "symbol": resolved_symbol,
            "explicit_symbol": explicit_symbol,
            "market": safe_market,
            "timeframe": resolved_timeframe,
            "explicit_timeframe": explicit_timeframe,
            "durations": durations,
            "numbers": numbers,
        },
        parameters={"symbol": resolved_symbol, "market": safe_market, "timeframe": resolved_timeframe},
        constraints=constraints,
        context_references=references,
        confidence=confidence,
        confidence_reasons=tuple(reasons),
        clarification_required=needs_clarification,
        clarification_question=clarification,
    )
