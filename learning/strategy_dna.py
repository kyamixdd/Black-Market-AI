"""Strategy DNA: auditable strategy specifications and paper-vs-backtest drift checks.

This module deliberately reports unavailable metrics as None. It never creates a
composite strategy score or infers profitability from a behavioral fingerprint.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import sqrt
from typing import Any

MIN_BASELINE_TRADES = 30
MIN_CURRENT_TRADES = 20
MIN_RATE_CHANGE_PP = 10.0
MIN_DRAWDOWN_CHANGE_PP = 3.0
MIN_DRAWDOWN_MULTIPLE = 1.5
MIN_FREQUENCY_RATIO = 2.0
MIN_HOLDING_RATIO = 2.0
PAPER_WINDOW_DAYS = 30

STRATEGY_DNA = {
    "momentum": {
        "type": "Momentum",
        "timeframes": ["15m"],
        "entry": "RSI > 55 with positive MACD histogram and MACD above signal for long; RSI < 45 with negative histogram and MACD below signal for short.",
        "exit": "ATR-based stop at 2x ATR; targets at 2x and 4x ATR. Simulation exits at stop/target or end of test.",
        "known_limitations": ["Single primary 15m timeframe", "Indicator thresholds are fixed in the built-in implementation", "Paper-trade slippage is not persisted in trade history"],
    },
    "breakout": {
        "type": "Breakout",
        "timeframes": ["15m"],
        "entry": "Close breaks the prior 20-bar high/low with volume expansion of at least 1.3x.",
        "exit": "Stop around the broken level using 1x ATR; targets at 2.5x and 5x ATR.",
        "known_limitations": ["Fixed 20-bar consolidation window", "Volume expansion is a binary filter", "Paper-trade slippage is not persisted in trade history"],
    },
    "trend_following": {
        "type": "Trend following",
        "timeframes": ["1h"],
        "entry": "Price above SMA20 above SMA50 for long; price below SMA20 below SMA50 for short.",
        "exit": "Stop beyond SMA20 by 1x ATR; targets at 3x and 6x ATR.",
        "known_limitations": ["Single primary 1h timeframe", "Fixed moving-average periods", "Paper-trade slippage is not persisted in trade history"],
    },
    "mean_reversion": {
        "type": "Mean reversion",
        "timeframes": ["15m"],
        "entry": "Price touches/exceeds a 20-period Bollinger band (2 standard deviations) with RSI below 30 or above 70.",
        "exit": "Fixed 1.5% stop; targets reference Bollinger middle/opposite band.",
        "known_limitations": ["Can remain exposed during persistent trends", "Fixed Bollinger and RSI parameters", "Paper-trade slippage is not persisted in trade history"],
    },
    "reversal": {
        "type": "Reversal",
        "timeframes": ["15m"],
        "entry": "See the strategy implementation for its reversal-specific candle/indicator conditions.",
        "exit": "Signal-provided stop and take-profit levels; simulator applies configured risk and execution rules.",
        "known_limitations": ["Detailed entry conditions depend on implementation and market data", "Paper-trade slippage is not persisted in trade history"],
    },
}

def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Strategy Lab timestamps are epoch milliseconds.
        return datetime.fromtimestamp(float(value) / 1000.0, timezone.utc)
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

def _closed(records: list[dict], strategy: str | None = None) -> list[dict]:
    output = []
    for row in records:
        if not isinstance(row, dict):
            continue
        if strategy and str(row.get("strategy", row.get("strategy_name", ""))).lower() != strategy:
            continue
        status = str(row.get("status", "")).upper()
        if status and status not in {"CLOSED", "COMPLETED", "OK"}:
            continue
        pnl = row.get("net_pnl", row.get("pnl"))
        try:
            pnl = float(pnl)
        except (TypeError, ValueError, OverflowError):
            continue
        if pnl != pnl or pnl in (float("inf"), float("-inf")):
            continue
        entry = _dt(row.get("entry_time", row.get("opened_at", row.get("entry_timestamp"))))
        exit_ = _dt(row.get("exit_time", row.get("closed_at", row.get("exit_timestamp"))))
        output.append({**row, "_pnl": pnl, "_entry": entry, "_exit": exit_})
    return output

def _behavior(records: list[dict], *, source: str, baseline_metrics: dict | None = None,
              capital: float | None = None, period_days: float | None = None) -> dict:
    trades = _closed(records)
    pnls = [t["_pnl"] for t in trades]
    wins = sum(x > 0 for x in pnls)
    losses = sum(x < 0 for x in pnls)
    timestamps = [t["_exit"] for t in trades if t["_exit"]]
    if period_days is None and len(timestamps) >= 2:
        period_days = max((max(timestamps) - min(timestamps)).total_seconds() / 86400.0, 1.0 / 24.0)
    frequency = len(trades) / period_days if period_days and period_days > 0 else None
    holds = [(t["_exit"] - t["_entry"]).total_seconds() / 60.0 for t in trades
             if t["_entry"] and t["_exit"] and t["_exit"] >= t["_entry"]]
    dd = None
    if baseline_metrics and isinstance(baseline_metrics.get("max_drawdown_pct"), (int, float)):
        dd = float(baseline_metrics["max_drawdown_pct"])
    elif capital and capital > 0:
        equity = peak = float(capital)
        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            if peak > 0:
                value = (peak - equity) / peak * 100.0
                dd = max(dd or 0.0, value)
    slips = []
    for t in trades:
        value = t.get("slippage_bps", t.get("slippage"))
        try:
            value = float(value)
            if value == value and abs(value) != float("inf"):
                slips.append(value)
        except (TypeError, ValueError, OverflowError):
            pass
    regimes: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "net_pnl": 0.0})
    for t in trades:
        regime = str(t.get("regime") or "UNKNOWN").upper()
        regimes[regime]["trades"] += 1
        regimes[regime]["wins"] += int(t["_pnl"] > 0)
        regimes[regime]["net_pnl"] += t["_pnl"]
    return {
        "source": source, "sample_size": len(trades),
        "win_rate_pct": wins / len(trades) * 100.0 if trades else None,
        "net_pnl": sum(pnls) if trades else None,
        "trade_frequency_per_day": frequency,
        "average_holding_minutes": sum(holds) / len(holds) if holds else None,
        "max_drawdown_pct": dd,
        "average_slippage_bps": sum(slips) / len(slips) if slips else None,
        "slippage_sample_size": len(slips),
        "by_regime": {k: {**v, "win_rate_pct": v["wins"] / v["trades"] * 100.0 if v["trades"] else None}
                      for k, v in regimes.items()},
        "limitations": (["Trade timestamps are incomplete; frequency/holding time may be unavailable."]
                       if len(holds) != len(trades) else []),
    }

def _wilson_lower(n: int, p: float, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    den = 1.0 + z*z/n
    center = p + z*z/(2*n)
    margin = z * sqrt(max(0.0, p*(1-p)/n + z*z/(4*n*n)))
    return (center - margin) / den

def evaluate_degradation(historical: dict, current: dict) -> dict:
    """Compare independent samples; low sample sizes are inconclusive, not warnings."""
    warnings = []
    reasons = []
    hn, cn = int(historical.get("sample_size") or 0), int(current.get("sample_size") or 0)
    result = {"status": "INSUFFICIENT_DATA", "warnings": warnings, "comparisons": {},
              "baseline_sample_size": hn, "current_sample_size": cn}
    if hn < MIN_BASELINE_TRADES or cn < MIN_CURRENT_TRADES:
        result["reason"] = f"Need at least {MIN_BASELINE_TRADES} historical and {MIN_CURRENT_TRADES} current closed trades."
        return result
    result["status"] = "STABLE"
    old, new = historical.get("win_rate_pct"), current.get("win_rate_pct")
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        change = float(new) - float(old)
        pooled = ((float(old)/100*hn) + (float(new)/100*cn)) / (hn+cn)
        se = sqrt(max(0.0, pooled*(1-pooled)*(1/hn+1/cn))) * 100
        threshold = max(MIN_RATE_CHANGE_PP, 2.0*se)
        flagged = change <= -threshold
        result["comparisons"]["win_rate_change_pp"] = {"value": change, "threshold_pp": threshold, "flagged": flagged}
        if flagged:
            warnings.append("WIN_RATE_DECLINE")
            reasons.append(f"Win rate decreased {abs(change):.1f} percentage points (sample-aware threshold {threshold:.1f}).")
    old, new = historical.get("max_drawdown_pct"), current.get("max_drawdown_pct")
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        threshold = max(MIN_DRAWDOWN_CHANGE_PP, abs(float(old))*(MIN_DRAWDOWN_MULTIPLE-1))
        change = float(new)-float(old)
        flagged = change >= threshold
        result["comparisons"]["drawdown_change_pp"] = {"value": change, "threshold_pp": threshold, "flagged": flagged}
        if flagged:
            warnings.append("DRAWDOWN_EXPANSION")
            reasons.append(f"Drawdown expanded {change:.1f} percentage points.")
    for key, warning in (("trade_frequency_per_day", "TRADE_FREQUENCY_SHIFT"),
                          ("average_holding_minutes", "HOLDING_TIME_SHIFT")):
        old, new = historical.get(key), current.get(key)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old > 0 and new >= 0:
            ratio = max(new/old if old else 0, old/new if new else float("inf"))
            flagged = ratio >= MIN_FREQUENCY_RATIO
            result["comparisons"][key] = {"historical": old, "current": new, "ratio": ratio if ratio != float("inf") else None, "flagged": flagged}
            if flagged:
                warnings.append(warning)
                reasons.append(f"{key.replace('_',' ')} changed by at least {MIN_FREQUENCY_RATIO:g}x.")
    old, new = historical.get("average_slippage_bps"), current.get("average_slippage_bps")
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        flagged = float(new)-float(old) >= max(2.0, abs(float(old)))
        result["comparisons"]["slippage_change_bps"] = {"value": float(new)-float(old), "flagged": flagged}
        if flagged:
            warnings.append("SLIPPAGE_INCREASE")
            reasons.append("Average slippage increased materially.")
    else:
        result["comparisons"]["slippage_change_bps"] = {"available": False, "reason": "Paper-trade records do not persist slippage; no estimate was substituted."}
    old_regimes, new_regimes = historical.get("by_regime") or {}, current.get("by_regime") or {}
    old_known = {k for k in old_regimes if k != "UNKNOWN"}
    new_known = {k for k in new_regimes if k != "UNKNOWN"}
    if old_known and new_known:
        changed = old_known != new_known
        result["comparisons"]["regime_change"] = {"historical_regimes": sorted(old_known), "current_regimes": sorted(new_known), "changed": changed}
        if changed:
            warnings.append("REGIME_MIX_CHANGED")
            reasons.append("The recorded trade regime mix differs from historical trades; this is contextual, not a forecast.")
    else:
        result["comparisons"]["regime_change"] = {"available": False, "reason": "Trade records do not contain sufficient regime labels."}
    if warnings:
        result["status"] = "DEGRADATION_DETECTED"
    result["reasons"] = reasons
    result["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    return result

def build_strategy_dna(reports: list[dict], paper_trades: list[dict], *, now: datetime | None = None,
                       capital: float | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=PAPER_WINDOW_DAYS)
    profiles = []
    keys = sorted(STRATEGY_DNA)
    for key in keys:
        spec = STRATEGY_DNA[key]
        report_records, report_periods, baseline_metrics, risk_config = [], [], [], []
        for report in reports:
            name = str(report.get("strategy_name", "")).lower()
            if name != key or report.get("status") not in {"ok", "completed", "saved"}:
                continue
            result = report.get("report") or {}
            trades = result.get("trades") if isinstance(result, dict) else None
            if isinstance(trades, list):
                report_records.extend(trades)
            metrics = result.get("metrics") if isinstance(result, dict) else {}
            if isinstance(metrics, dict):
                baseline_metrics.append(metrics)
            config = report.get("config") or {}
            if isinstance(config, dict):
                risk_config.append({k: config.get(k) for k in ("risk_per_trade_pct", "max_position_pct", "sizing_mode", "initial_capital") if k in config})
                start, end = _dt(config.get("start_date")), _dt(config.get("end_date"))
                if start and end and end > start:
                    report_periods.append((end-start).total_seconds()/86400)
        paper = []
        for trade in paper_trades:
            if str(trade.get("strategy") or "").lower() != key:
                continue
            closed = _dt(trade.get("closed_at"))
            if closed and closed >= cutoff:
                paper.append(trade)
        historical = _behavior(report_records, source="backtest", baseline_metrics={
            "max_drawdown_pct": max((m.get("max_drawdown_pct", 0) for m in baseline_metrics
                                    if isinstance(m.get("max_drawdown_pct"), (int,float))), default=0)
        } if baseline_metrics else None,
            period_days=sum(report_periods) if report_periods else None)
        current = _behavior(paper, source="paper_trading", capital=capital, period_days=PAPER_WINDOW_DAYS)
        evaluation = evaluate_degradation(historical, current)
        profiles.append({
            "strategy": key, "strategy_type": spec["type"],
            "supported_assets": ["Exchange-listed symbols supported by the configured market data feed"],
            "supported_markets": ["SPOT", "FUTURES"],
            "supported_timeframes": spec["timeframes"],
            "entry_conditions": spec["entry"], "exit_conditions": spec["exit"],
            "risk_configuration": risk_config[-1] if risk_config else None,
            "historical_behavior": historical, "current_paper_behavior": current,
            "behavioral_differences": evaluation,
            "sample_size": {"historical_trades": historical["sample_size"], "current_paper_trades": current["sample_size"]},
            "last_evaluated_at": evaluation.get("evaluated_at"),
            "known_limitations": spec["known_limitations"],
        })
    return {"profiles": profiles, "window_days": PAPER_WINDOW_DAYS,
            "methodology": "Behavioral diagnostics only; no composite score and no prediction of future profitability."}
