"""Deterministic, evidence-based market regime radar.

Classification is a descriptive rule set, not a predictive or statistically calibrated model.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable


def _valid_candles(rows: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    valid = []
    for row in rows:
        try:
            values = {key: float(row[key]) for key in ("open", "high", "low", "close", "volume")}
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(value) for value in values.values()):
            continue
        if min(values["open"], values["high"], values["low"], values["close"]) <= 0 or values["volume"] < 0:
            continue
        if values["high"] < max(values["open"], values["close"], values["low"]) or values["low"] > min(values["open"], values["close"]):
            continue
        valid.append(values)
    return valid


def classify_market_regime(
    candles: Iterable[dict[str, Any]],
    *,
    symbol: str,
    market: str,
    timeframe: str,
    expected_candles: int = 100,
) -> dict[str, Any]:
    """Return rule-based regime and evidence with explicit data sufficiency."""
    rows = _valid_candles(candles)
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]
    completeness = min(1.0, len(rows) / max(1, expected_candles))
    timestamp = datetime.now(timezone.utc).isoformat()
    base = {
        "symbol": symbol.upper(), "market": market.upper(), "timeframe": timeframe,
        "classified_at": timestamp, "data_completeness": round(completeness, 4),
        "sample_count": len(rows), "expected_sample_count": expected_candles,
        "classification_confidence": None, "confidence_type": "not_statistically_calibrated",
        "supporting_indicators": {}, "evidence": [], "limitations": [
            "Rule-based descriptive classification; not a prediction or calibrated probability.",
            "Historical candles may be delayed or incomplete; verify freshness before acting.",
        ],
    }
    if len(closes) < 50:
        return {**base, "regime": "INSUFFICIENT_DATA", "status": "INSUFFICIENT_DATA",
                "evidence": [f"Need at least 50 valid candles; received {len(closes)}."]}

    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50
    slope_pct = (closes[-1] / closes[-20] - 1.0) * 100.0
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 20, len(closes))]
    realized_vol_pct = math.sqrt(sum(value * value for value in returns)) * 100.0
    avg_volume = sum(volumes[-20:]) / 20
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else None

    indicators = {
        "close": closes[-1], "sma20": sma20, "sma50": sma50,
        "slope_20_candles_pct": slope_pct,
        "realized_volatility_20_candles_pct": realized_vol_pct,
        "latest_volume": volumes[-1], "average_volume_20_candles": avg_volume,
        "latest_volume_ratio": volume_ratio,
    }
    evidence: list[str] = []
    if realized_vol_pct >= 2.5:
        regime = "HIGH_VOLATILITY"
        evidence.append(f"20-candle realized volatility is {realized_vol_pct:.3f}%, above the 2.5% rule threshold.")
    elif realized_vol_pct <= 0.45:
        regime = "LOW_VOLATILITY"
        evidence.append(f"20-candle realized volatility is {realized_vol_pct:.3f}%, below the 0.45% rule threshold.")
    elif closes[-1] > sma20 > sma50 and slope_pct >= 0.5:
        regime = "UPTREND"
        evidence.extend(["Latest close is above SMA20 and SMA20 is above SMA50.",
                         f"20-candle price change is +{slope_pct:.3f}%."])
    elif closes[-1] < sma20 < sma50 and slope_pct <= -0.5:
        regime = "DOWNTREND"
        evidence.extend(["Latest close is below SMA20 and SMA20 is below SMA50.",
                         f"20-candle price change is {slope_pct:.3f}%."])
    elif abs(slope_pct) < 0.5:
        regime = "RANGE_BOUND"
        evidence.append(f"Absolute 20-candle price change is {abs(slope_pct):.3f}%, below the 0.5% trend threshold.")
    else:
        regime = "MIXED"
        evidence.append("Trend alignment does not meet the defined uptrend, downtrend, or range-bound rules.")

    # No calibrated confidence model is available; avoid publishing a pseudo-probability.\n    if volume_ratio is not None:
        evidence.append(f"Latest volume is {volume_ratio:.2f}x the 20-candle average.")
    return {
        **base, "regime": regime, "status": "READY",
        "classification_confidence": None,
        "supporting_indicators": indicators, "evidence": evidence,
    }
