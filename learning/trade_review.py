"""Evidence-first post-trade review that separates process from P&L."""
from __future__ import annotations

import math
from typing import Any


def build_trade_review(trade: dict[str, Any], signal: dict[str, Any] | None = None,
                      regime: dict[str, Any] | None = None) -> dict[str, Any]:
    """Review one actual closed trade; missing execution trace remains unknown."""
    evidence = [{
        "source": "paper_trade_record",
        "record_id": str(trade.get("position_id", "")),
        "fields": ["symbol", "market", "side", "entry_price", "exit_price",
                   "amount", "leverage", "pnl", "pnl_pct", "fee",
                   "opened_at", "closed_at", "close_reason"],
    }]
    observed = {key: trade.get(key) for key in (
        "symbol", "market", "side", "entry_price", "exit_price", "amount",
        "leverage", "pnl", "pnl_pct", "fee", "strategy", "opened_at",
        "closed_at", "close_reason", "position_id",
    )}
    issues = []
    signal_check = "UNAVAILABLE"
    if signal:
        signal_check = "AVAILABLE"
        evidence.append({
            "source": "signal_record", "record_id": str(signal.get("signal_id", "")),
            "fields": ["strategy", "direction", "entry", "stop_loss", "take_profit", "reasons"],
        })
        signal_strategy = str(signal.get("strategy", "")).upper()
        trade_strategy = str(trade.get("strategy", "")).upper()
        if signal_strategy and trade_strategy and signal_strategy != trade_strategy:
            issues.append("Trade strategy label differs from linked signal strategy.")
        try:
            expected_entry = float(signal["entry"])
            actual_entry = float(trade["entry_price"])
            if not all(math.isfinite(value) for value in (expected_entry, actual_entry)) or expected_entry <= 0:
                raise ValueError
            deviation_pct = abs(actual_entry - expected_entry) / expected_entry * 100.0
        except (KeyError, TypeError, ValueError, OverflowError):
            deviation_pct = None
    else:
        deviation_pct = None
        issues.append("No linked signal record; entry and strategy conditions cannot be reconstructed.")

    try:
        pnl = float(trade["pnl"])
        outcome = "PROFIT" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
    except (KeyError, TypeError, ValueError, OverflowError):
        outcome = "UNKNOWN"

    return {
        "review_version": 1,
        "trade_id": str(trade.get("position_id", "")),
        "observed_trade": observed,
        "outcome": outcome,
        "decision_quality": "NOT_RATED",
        "strategy_rule_adherence": "UNVERIFIABLE",
        "position_sizing_compliance": "UNVERIFIABLE",
        "risk_limit_compliance": "UNVERIFIABLE",
        "signal_link_status": signal_check,
        "entry_price_deviation_pct": deviation_pct,
        "market_regime_at_entry": regime if regime and regime.get("status") == "READY" else {
            "status": "UNAVAILABLE",
            "reason": "Historical entry-time regime could not be calculated from available candles.",
        },
        "findings": issues + [
            "Profit or loss is reported as outcome, not used as a decision-quality grade.",
            "A full rule-adherence trace and risk snapshot were not persisted with this trade.",
        ],
        "evidence": evidence,
        "limitations": [
            "This is a factual review, not a strategy-performance prediction.",
            "Missing strategy execution logs prevent a verified adherence verdict.",
        ],
    }
