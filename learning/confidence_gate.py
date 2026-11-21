"""Historical confidence threshold selection and model promotion safety gate."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Any
import numpy as np
from config import MIN_VALIDATION_F1, WALK_FORWARD_MIN_SAMPLES

def select_confidence_threshold(probabilities: Any, forward_returns: Any, *, fee_rate: float = 0.0004, candidates: tuple[float, ...] = tuple(round(x, 2) for x in np.arange(0.50, 0.86, 0.05)), min_trades: int = 10) -> dict[str, Any]:
    """Select a confidence cutoff using prior, chronologically held-out calibration outcomes."""
    probs = np.asarray(probabilities, dtype=float).reshape(-1)
    returns = np.asarray(forward_returns, dtype=float).reshape(-1)
    if len(probs) != len(returns) or not len(probs):
        return {"threshold": 1.01, "status": "insufficient_calibration", "calibration_samples": 0, "candidate_results": []}
    if not np.isfinite(probs).all() or not np.isfinite(returns).all() or np.any((probs < 0) | (probs > 1)):
        raise ValueError("probabilities must be finite in [0,1] and returns finite")
    if not 0 <= fee_rate < 0.1 or min_trades < 1:
        raise ValueError("invalid fee_rate or min_trades")
    confidence = np.maximum(probs, 1.0 - probs)
    direction = np.where(probs >= 0.5, 1.0, -1.0)
    evaluations = []
    for threshold in candidates:
        threshold = float(threshold)
        if not 0.5 <= threshold <= 1.0:
            continue
        active = confidence >= threshold
        count = int(active.sum())
        if count < min_trades:
            continue
        signal = np.where(active, direction, 0.0)
        fees = np.abs(np.diff(np.concatenate(([0.0], signal)))) * fee_rate
        if signal[-1] != 0:
            fees[-1] += fee_rate
        # Attribute exit fees to the last active observation so threshold
        # expectancy cannot omit costs merely because the position is flat
        # on the row where the exit transition is recorded.
        for index in np.flatnonzero(~active & (fees > 0)):
            previous_active = np.flatnonzero(active[:index])
            if previous_active.size:
                fees[previous_active[-1]] += fees[index]
                fees[index] = 0.0
        net = signal * returns - fees
        active_net = net[active]
        gains = float(active_net[active_net > 0].sum())
        losses = abs(float(active_net[active_net < 0].sum()))
        equity = np.cumprod(1.0 + net)
        peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
        dd = (peaks - equity) / np.maximum(peaks, 1e-12)
        evaluations.append({"threshold": threshold, "trades": count, "coverage_pct": count / len(probs) * 100.0, "net_expectancy_per_trade": float(active_net.mean()), "net_return_pct": float((equity[-1] - 1.0) * 100.0), "max_drawdown_pct": float(dd.max()) * 100.0 if len(dd) else 0.0, "win_rate_pct": float((active_net > 0).mean()) * 100.0, "profit_factor": gains / losses if losses else (None if gains == 0 else "infinite")})
    if not evaluations:
        return {"threshold": 1.01, "status": "no_threshold_met_minimum_trades", "calibration_samples": len(probs), "candidate_results": []}
    best = max(evaluations, key=lambda row: (row["net_expectancy_per_trade"], -row["max_drawdown_pct"], row["coverage_pct"]))
    return {"threshold": best["threshold"], "status": "selected_from_historical_calibration", "calibration_samples": len(probs), "selected_metrics": best, "candidate_results": evaluations, "selection_objective": "maximum net expectancy after fees; tie-break lower drawdown then coverage"}

@dataclass(frozen=True)
class PromotionGateCriteria:
    min_samples: int = WALK_FORWARD_MIN_SAMPLES
    min_folds: int = 3
    min_mean_f1: float = MIN_VALIDATION_F1
    max_fold_degradation: float = 0.12

class ModelPromotionGate:
    """Fail-closed model promotion gate; challenger cannot activate unless all checks pass."""
    def __init__(self, criteria: PromotionGateCriteria | None = None):
        self.criteria = criteria or PromotionGateCriteria()
    def evaluate(self, validation: dict[str, Any], sample_count: int) -> dict[str, Any]:
        c = self.criteria
        reasons: list[str] = []
        if sample_count < c.min_samples:
            reasons.append(f"sample_count {sample_count} below required {c.min_samples}")
        model_results = {}
        for name in ("rf", "xgb"):
            result = validation.get(name) or {}
            folds = result.get("folds") or []
            mean_f1 = _finite((result.get("aggregated") or {}).get("mean_f1"))
            failures = []
            if not result.get("valid") or not result.get("passes_threshold"):
                failures.append("walk-forward validation did not pass configured threshold")
            if len(folds) < c.min_folds:
                failures.append(f"only {len(folds)} folds; require {c.min_folds}")
            if mean_f1 is None or mean_f1 < c.min_mean_f1:
                failures.append(f"mean F1 below configured threshold {c.min_mean_f1:.3f}")
            scores = []
            for fold in folds:
                score = _finite(fold.get("f1_macro"))
                train_end, test_start = fold.get("train_end_index"), fold.get("test_start_index")
                if score is None:
                    failures.append("fold has missing/non-finite F1")
                else:
                    scores.append(score)
                if train_end is None or test_start is None or int(train_end) >= int(test_start):
                    failures.append("training window overlaps or follows test window")
            if mean_f1 is not None and scores and min(scores) < mean_f1 - c.max_fold_degradation:
                failures.append(f"weakest fold exceeds allowed degradation {c.max_fold_degradation:.3f}")
            model_results[name] = {"passes": not failures, "mean_f1": mean_f1, "fold_count": len(folds), "failure_reasons": failures}
            reasons.extend(f"{name}: {failure}" for failure in failures)
        if not validation.get("ensemble_passes", False):
            reasons.append("both RF and XGBoost must pass existing validation")
        return {"passes": not reasons, "criteria": {"min_samples": c.min_samples, "min_folds": c.min_folds, "min_mean_f1": c.min_mean_f1, "max_fold_degradation": c.max_fold_degradation}, "models": model_results, "failure_reasons": reasons, "policy": "fail closed; activation requires every check"}

def _finite(value: Any) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return number if isfinite(number) else None
