"""Deterministic market analytics with explicit insufficiency handling."""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def _finite_positive(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    if array.ndim != 1 or not np.isfinite(array).all() or (array <= 0).any():
        return np.array([], dtype=float)
    return array


def historical_volatility(closes: Iterable[float], window: int = 24) -> float | None:
    """24-hour realized volatility in percent from hourly close-to-close returns."""
    values = _finite_positive(closes)
    if window < 2 or len(values) < window + 1:
        return None
    returns = np.diff(np.log(values[-(window + 1):]))
    if not np.isfinite(returns).all():
        return None
    return float(math.sqrt(float(np.sum(np.square(returns)))) * 100.0)


def volume_comparison(volumes: Iterable[float], baseline_window: int = 20) -> dict:
    """Compare latest candle volume to a full prior baseline; no partial-window fallback."""
    values = np.asarray(list(volumes), dtype=float)
    if baseline_window < 1 or len(values) < baseline_window + 1:
        return {"latest": None, "average": None, "ratio": None, "change_pct": None,
                "status": "INSUFFICIENT_DATA", "baseline_count": max(0, len(values) - 1)}
    baseline = values[-baseline_window - 1:-1]
    latest = float(values[-1])
    if not np.isfinite(values).all() or (values < 0).any():
        return {"latest": None, "average": None, "ratio": None, "change_pct": None,
                "status": "INVALID_DATA", "baseline_count": baseline_window}
    average = float(np.mean(baseline))
    if average <= 0:
        return {"latest": latest, "average": average, "ratio": None, "change_pct": None,
                "status": "ZERO_BASELINE", "baseline_count": baseline_window}
    ratio = latest / average
    return {"latest": latest, "average": average, "ratio": ratio,
            "change_pct": (ratio - 1.0) * 100.0, "status": "READY",
            "baseline_count": baseline_window}


def price_change(closes: Iterable[float], periods: int) -> float | None:
    """Percent change over a specified number of close-to-close intervals."""
    values = _finite_positive(closes)
    if periods < 1 or len(values) <= periods:
        return None
    return float((values[-1] / values[-periods - 1] - 1.0) * 100.0)


def return_correlation(left_closes: Iterable[float], right_closes: Iterable[float],
                        minimum_returns: int = 20) -> float | None:
    """Pearson correlation of aligned close-to-close returns, requiring a full sample."""
    left = _finite_positive(left_closes)
    right = _finite_positive(right_closes)
    count = min(len(left), len(right))
    if count <= minimum_returns:
        return None
    left_returns = np.diff(np.log(left[-count:]))
    right_returns = np.diff(np.log(right[-count:]))
    if len(left_returns) < minimum_returns or not np.isfinite(left_returns).all() or not np.isfinite(right_returns).all():
        return None
    if np.std(left_returns) == 0 or np.std(right_returns) == 0:
        return None
    return float(np.corrcoef(left_returns, right_returns)[0, 1])


def breadth_summary(changes: Iterable[float]) -> dict:
    """Advance/decline statistics over the supplied valid price-change sample."""
    values = [float(value) for value in changes if value is not None and math.isfinite(float(value))]
    advancing = sum(value > 0 for value in values)
    declining = sum(value < 0 for value in values)
    neutral = sum(value == 0 for value in values)
    total = len(values)
    return {
        "advancing": advancing, "declining": declining, "neutral": neutral,
        "sample_size": total,
        "advance_pct": advancing / total * 100.0 if total else None,
        "decline_pct": declining / total * 100.0 if total else None,
        "neutral_pct": neutral / total * 100.0 if total else None,
        "advance_decline_ratio": advancing / declining if declining else None,
        "status": "READY" if total else "UNAVAILABLE",
    }
