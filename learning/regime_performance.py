"""Aggregate completed Strategy Lab trades by supplied historical regime labels.

Regime labels must be calculated from candles available at or before each entry.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from typing import Any, Iterable


def performance_by_regime(
    trades: Iterable[dict[str, Any]],
    regime_observations: Iterable[dict[str, Any]],
    *,
    minimum_sample: int = 5,
    initial_capital: float = 1000.0,
) -> dict[str, Any]:
    observations = []
    for row in regime_observations:
        try:
            timestamp = int(row["timestamp"])
            label = str(row["regime"]).strip().upper()
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if label and label not in {"UNKNOWN", "INSUFFICIENT_DATA"}:
            observations.append((timestamp, label))
    observations.sort()
    times = [item[0] for item in observations]
    grouped: dict[str, list[dict[str, float]]] = defaultdict(list)
    unclassified = 0

    for trade in trades:
        if str(trade.get("status", "")).upper() != "CLOSED":
            continue
        try:
            entry_time = int(trade["entry_time"])
            exit_time = int(trade["exit_time"])
            net = float(trade["net_pnl"])
            quantity = float(trade["quantity"])
            entry = float(trade["entry_fill"] if "entry_fill" in trade else trade["entry_price"])
            if not all(math.isfinite(value) for value in (net, quantity, entry)):
                continue
            if quantity <= 0 or entry <= 0 or exit_time < entry_time:
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        idx = bisect_right(times, entry_time) - 1
        if idx < 0:
            unclassified += 1
            continue
        regime = observations[idx][1]
        grouped[regime].append({
            "net_pnl": net,
            "notional": quantity * entry,
            "holding_hours": (exit_time - entry_time) / 3_600_000.0,
            "entry_time": float(entry_time),
        })

    result = {}
    for regime, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["entry_time"])
        pnls = [row["net_pnl"] for row in rows]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        equity = peak = float(initial_capital)
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        for value in pnls:
            equity += value
            peak = max(peak, equity)
            drawdown = peak - equity
            max_drawdown = max(max_drawdown, drawdown)
            if peak > 0:
                max_drawdown_pct = max(max_drawdown_pct, drawdown / peak * 100.0)
        count = len(rows)
        total_notional = sum(row["notional"] for row in rows)
        result[regime] = {
            "trade_count": count,
            "sample_status": "READY" if count >= minimum_sample else "INSUFFICIENT_SAMPLE",
            "net_return_pct": sum(pnls) / total_notional * 100.0 if total_notional > 0 else None,
            "net_pnl": sum(pnls),
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "win_rate_pct": len(wins) / count * 100.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "average_holding_hours": sum(row["holding_hours"] for row in rows) / count,
            "limitations": [
                "Historical regime association; not a forecast.",
                "Regime observations must be calculated without future candles.",
                "Drawdown is calculated on the configured starting capital and regime-filtered trade sequence.",
            ],
        }
    return {
        "regimes": result,
        "unclassified_trades": unclassified,
        "minimum_sample": minimum_sample,
        "drawdown_initial_capital": initial_capital,
        "status": "READY" if result else "INSUFFICIENT_DATA",
    }
