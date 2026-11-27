"""Deterministic natural-language understanding for supported assistant requests."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4
from typing import Any

from config import SUPPORTED_TIMEFRAMES
from .assistant_intelligence import validate_market, validate_symbol

TIMEFRAMES = set(SUPPORTED_TIMEFRAMES)
COMMON_ASSETS = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "LTC", "TRX", "TON", "BCH"}
_TIMEFRAME_RE = re.compile(
    r"(?<![a-z0-9])(" + "|".join(map(re.escape, SUPPORTED_TIMEFRAMES)) + r")(?![a-z0-9])",
    re.I,
)
_TIMEFRAME_WORD_RE = re.compile(r"\b(1|3|5|15|30)\s*(?:-?minutes?|mins?)\b|\b(1|4)\s*(?:-?hours?|hrs?)\b|\b(daily|weekly)\b", re.I)
_PAIR_RE = re.compile(r"\b([A-Z0-9]{2,12})(USDT|USDC|USD|BTC|ETH)\b", re.I)
_DURATION_RE = re.compile(r"\b(?:last|past|over|for)\s+(\d+)\s+(minute|hour|day|week|month|year)s?\b", re.I)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class ContextSnapshot:
    symbol: str | None = None
    timeframe: str | None = None
    previous_query: str | None = None
    previous_tool: str | None = None


@dataclass(frozen=True)
class ParsedIntent:
    name: str
    tool: str
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


_INTENT_GROUPS = (
    ("historical_data", "historical_candles", ("historical", "history", "candles", "ohlc")),
    ("indicators", "indicator_report", ("indicator", "indicators", "sma", "ema", "atr", "volatility", "analytics")),
    ("scanner", "scanner_status", ("scanner", "scan status")),
    ("signals", "signal_report", ("signal", "signals", "rejected signal")),
    ("strategy", "strategy_report", ("strategy", "backtest", "weights")),
    ("positions", "open_positions", ("position", "positions", "open trade", "open trades")),
    ("trade_history", "trade_history", ("trade history", "closed trade", "recent trade")),
    ("risk", "risk_status", ("risk", "exposure", "risk limit")),
    ("learning", "learning_evaluation", ("learning", "model evaluation", "accuracy", "prediction")),
    ("paper_account", "paper_account", ("paper account", "equity", "balance", "pnl", "portfolio")),
    ("market_snapshot", "market_snapshot", ("market", "price", "regime", "analyze", "analyse", "compare")),
)


def _find_intents(text: str) -> list[ParsedIntent]:
    found = []
    for name, tool, terms in _INTENT_GROUPS:
        matches = tuple(term for term in terms if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text))
        if matches:
            found.append((min(text.find(term) for term in matches), ParsedIntent(name, tool, matches)))
    found.sort(key=lambda item: item[0])
    # One intent category may have several trigger words; keep one record per category.
    intents = [item[1] for item in found]
    matched_tools = {intent.tool for intent in intents}
    filtered: list[ParsedIntent] = []
    for intent in intents:
        if (
            intent.tool == "market_snapshot"
            and "scanner_status" in matched_tools
            and intent.evidence_terms == ("market",)
            and not re.search(r"\bmarket\b(?!\s+scanner\b)", text)
        ):
            continue
        if (
            intent.tool == "historical_candles"
            and "trade_history" in matched_tools
            and intent.evidence_terms == ("history",)
            and not re.search(r"(?<!\btrade\s)\bhistory\b", text)
        ):
            continue
        if (
            intent.tool == "paper_account"
            and "risk_status" in matched_tools
            and intent.evidence_terms == ("portfolio",)
            and not re.search(r"\bportfolio\b(?!\s+(?:risk|exposure)\b)", text)
        ):
            continue
        filtered.append(intent)
    return filtered


def _extract_assets(text: str) -> list[str]:
    ordered: list[tuple[int, str]] = []
    upper = text.upper()
    pair_spans: list[tuple[int, int]] = []
    for match in _PAIR_RE.finditer(upper):
        pair_spans.append(match.span())
        pair = match.group(1) + match.group(2)
        try:
            ordered.append((match.start(), validate_symbol(pair)))
        except ValueError:
            continue
    asset_pattern = re.compile(r"\b(" + "|".join(sorted(COMMON_ASSETS)) + r")\b")
    for match in asset_pattern.finditer(upper):
        if any(start <= match.start() < end for start, end in pair_spans):
            continue
        ordered.append((match.start(), match.group(1) + "USDT"))
    ordered.sort(key=lambda item: item[0])
    return list(dict.fromkeys(asset for _, asset in ordered))

def parse_assistant_request(
    text: str,
    *,
    symbol: str = "BTCUSDT",
    market: str = "SPOT",
    timeframe: str = "1h",
    context: ContextSnapshot | None = None,
    request_id: str | None = None,
) -> StructuredAssistantRequest:
    """Extract supported intents, entities, parameters, references and ambiguity."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Assistant query must not be empty.")
    original = text.strip()
    normalized = re.sub(r"\s+", " ", original).lower()
    default_symbol = validate_symbol(symbol)
    default_market = validate_market(market)
    default_timeframe = timeframe.strip().lower()
    if default_timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported timeframe.")
    context = context or ContextSnapshot()

    intents = _find_intents(normalized)
    if not intents and re.search(r"\b(market|price|crypto|coin)\b", normalized):
        intents = [ParsedIntent("market_snapshot", "market_snapshot", ("market query",))]
    assets = _extract_assets(original)
    timeframe_match = _TIMEFRAME_RE.search(normalized)
    explicit_timeframe = timeframe_match.group(1).lower() if timeframe_match else None
    if not explicit_timeframe:
        word_match = _TIMEFRAME_WORD_RE.search(normalized)
        if word_match:
            if word_match.group(1):
                explicit_timeframe = word_match.group(1) + "m"
            elif word_match.group(2):
                explicit_timeframe = word_match.group(2) + "h"
            elif word_match.group(3):
                explicit_timeframe = "1d" if word_match.group(3).lower() == "daily" else "1w"
    references = tuple(ref for ref in ("it", "that asset", "same timeframe", "previous", "earlier", "last result", "continue", "again", "that strategy") if re.search(r"\b" + re.escape(ref) + r"\b", normalized))
    resolved_symbol = assets[0] if assets else (context.symbol if references and context.symbol else default_symbol)
    resolved_timeframe = explicit_timeframe or (context.timeframe if references and context.timeframe else default_timeframe)
    durations = [{"value": int(m.group(1)), "unit": m.group(2).lower()} for m in _DURATION_RE.finditer(normalized)]
    numbers = _NUMBER_RE.findall(normalized)
    constraint_phrases = ("exclude low-volume", "without low-volume", "only completed", "paper trading only", "exclude stale", "exclude low volume", "no low-volume")
    constraints = tuple(phrase for phrase in constraint_phrases if phrase in normalized)

    clarification = None
    unresolved_reference = False
    if not intents:
        clarification = "What market or application information should I retrieve?"
    elif references and not assets and not context.symbol:
        clarification = "Which asset are you referring to?"
        unresolved_reference = True
    elif "same timeframe" in references and not explicit_timeframe and not context.timeframe:
        clarification = "Which timeframe should I reuse?"
        unresolved_reference = True
    elif len(assets) > 1 and "compare" not in normalized and "versus" not in normalized and " vs " not in normalized:
        clarification = "Which asset should I analyze first?"
    needs_clarification = clarification is not None

    confidence = ConfidenceLevel.HIGH
    reasons = ["Supported intent terms were matched deterministically."]
    if len(intents) > 1 or len(assets) > 1:
        confidence = ConfidenceLevel.MEDIUM
        reasons.append("Multiple intent categories or assets were detected.")
    if not intents:
        confidence = ConfidenceLevel.LOW
        reasons.append("No supported intent category was identified.")
    if references and not (context.symbol or context.timeframe):
        confidence = ConfidenceLevel.LOW
        reasons.append("Reference resolution has no supplied prior context.")
    if not assets:
        reasons.append("Asset falls back to the validated request parameter or context.")

    unsupported = not intents
    resolved_intents = () if unresolved_reference else tuple(intents)
    return StructuredAssistantRequest(
        request_id=request_id or uuid4().hex,
        original_text=original,
        normalized_text=normalized,
        intents=resolved_intents,
        entities={
            "assets": assets,
            "symbol": resolved_symbol,
            "explicit_symbol": assets[0] if assets else None,
            "market": default_market,
            "timeframe": resolved_timeframe,
            "explicit_timeframe": explicit_timeframe,
            "durations": durations,
            "numbers": numbers,
        },
        parameters={"symbol": resolved_symbol, "market": default_market, "timeframe": resolved_timeframe},
        constraints=constraints,
        context_references=references,
        confidence=confidence,
        confidence_reasons=tuple(reasons),
        clarification_required=needs_clarification,
        clarification_question=clarification,
        unsupported=unsupported,
    )
