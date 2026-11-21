"""Historical confidence threshold selection and model promotion safety gate."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Any
import numpy as np
from config import MIN_VALIDATION_ACCURACY, MIN_VALIDATION_F1, WALK_FORWARD_MIN_SAMPLES

def select_confidence_threshold(probabilities: Any, forward_returns: Any, *, fee_rate: float = 0.0004, candidates: tuple[float, ...] = tuple(round(x, 2) for x in np.arange(0.50, 0.86, 0.05)), min_trades: int = 10, test_probabilities: Any = None, test_forward_returns: Any = None) -> dict[str, Any]:
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
    result = {"threshold": best["threshold"], "status": "selected_from_historical_calibration", "calibration_samples": len(probs), "selected_metrics": best, "candidate_results": evaluations, "selection_objective": "maximum net expectancy after fees; tie-break lower drawdown then coverage"}
    if (test_probabilities is None) != (test_forward_returns is None):
        raise ValueError("test_probabilities and test_forward_returns must be provided together")
    if test_probabilities is not None:
        heldout = select_confidence_threshold(
            test_probabilities, test_forward_returns, fee_rate=fee_rate,
            candidates=(best["threshold"],), min_trades=min_trades,
        )
        result["heldout_test_metrics"] = heldout.get("selected_metrics")
        result["heldout_test_status"] = heldout.get("status")
        result["test_samples"] = int(np.asarray(test_probabilities).size)
        result["calibration_test_boundary"] = "threshold selected using calibration arrays only; test arrays are evaluation-only"
    return result

@dataclass(frozen=True)
class PromotionGateCriteria:
    min_samples: int = WALK_FORWARD_MIN_SAMPLES
    min_folds: int = 3
    min_mean_accuracy: float = MIN_VALIDATION_ACCURACY
    min_mean_f1: float = MIN_VALIDATION_F1
    max_fold_degradation: float = 0.12
    min_net_expectancy: float = 0.0001
    max_drawdown_pct: float = 10.0
    min_calibration_score: float = 0.68
    min_stability_score: float = 0.60
    min_regime_coverage: int = 2
    min_regime_samples: int = 30
    min_improvement_over_champion: float = 0.02
    min_net_expectancy_improvement: float = 0.0001
    futures_funding_rate_per_8h: float = 0.0001


class ModelPromotionGate:
    """Fail-closed promotion gate using OOF classification and net trading evidence."""
    def __init__(self, criteria: PromotionGateCriteria | None = None):
        self.criteria = criteria or PromotionGateCriteria()

    def evaluate(
        self,
        validation: dict[str, Any],
        sample_count: int,
        *,
        economic_metadata: dict[str, Any] | None = None,
        champion_validation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        c = self.criteria
        reasons: list[str] = []
        if sample_count < c.min_samples:
            reasons.append(f"sample_count {sample_count} below required {c.min_samples}")
        model_results: dict[str, Any] = {}
        economic_by_model: dict[str, Any] = {}
        champion_by_model: dict[str, Any] = {}
        for name in ("rf", "xgb"):
            result = validation.get(name) or {}
            folds = result.get("folds") or []
            aggregated = result.get("aggregated") or {}
            mean_f1 = _finite(aggregated.get("mean_f1"))
            mean_accuracy = _finite(aggregated.get("mean_accuracy"))
            failures: list[str] = []
            if not result.get("valid") or not result.get("passes_threshold"):
                failures.append("walk-forward validation did not pass configured threshold")
            if len(folds) < c.min_folds:
                failures.append(f"only {len(folds)} folds; require {c.min_folds}")
            if mean_f1 is None or mean_f1 < c.min_mean_f1:
                failures.append(f"mean F1 below required {c.min_mean_f1:.3f}")
            if mean_accuracy is None or mean_accuracy < c.min_mean_accuracy:
                failures.append(f"mean accuracy below required {c.min_mean_accuracy:.3f}")
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
                failures.append(f"weakest fold exceeds allowed F1 degradation {c.max_fold_degradation:.3f}")

            oof = result.get("out_of_fold") or []
            if not oof:
                failures.append("out-of-fold predictions/probabilities missing")
            calibration_score = self._calibration_score(oof)
            if calibration_score is None or calibration_score < c.min_calibration_score:
                failures.append(f"calibration score below required {c.min_calibration_score:.3f}")

            economic = self._economic_evidence(oof, economic_metadata, folds)
            economic_by_model[name] = economic
            if economic.get("status") != "ok":
                failures.append("net expectancy/drawdown evidence unavailable: " + str(economic.get("reason")))
            else:
                if economic["net_expectancy"] < c.min_net_expectancy:
                    failures.append(f"net expectancy {economic['net_expectancy']:.6f} below required {c.min_net_expectancy:.6f}")
                if economic["max_drawdown_pct"] > c.max_drawdown_pct:
                    failures.append(f"drawdown {economic['max_drawdown_pct']:.2f}% exceeds {c.max_drawdown_pct:.2f}%")
                if economic["stability_score"] < c.min_stability_score:
                    failures.append(f"net-return stability below required {c.min_stability_score:.2f}")
                if economic["regime_coverage"] < c.min_regime_coverage:
                    failures.append(f"positive-net regime coverage {economic['regime_coverage']} below required {c.min_regime_coverage}")

            champion_result = (champion_validation or {}).get(name) or {}
            champion_oof = champion_result.get("out_of_fold") or []
            champion_f1 = _finite((champion_result.get("aggregated") or {}).get("mean_f1"))
            champion_economic = self._economic_evidence(champion_oof, economic_metadata, champion_result.get("folds") or [])
            champion_by_model[name] = champion_economic
            if not champion_result.get("valid") or not champion_oof or champion_f1 is None:
                failures.append("active champion comparison evidence missing")
            elif economic.get("status") == "ok" and champion_economic.get("status") == "ok":
                relative_f1 = (mean_f1 - champion_f1) / max(abs(champion_f1), 1e-6) if mean_f1 is not None else -1.0
                net_delta = economic["net_expectancy"] - champion_economic["net_expectancy"]
                economic["champion_f1"] = champion_f1
                economic["relative_f1_improvement"] = relative_f1
                economic["net_expectancy_improvement"] = net_delta
                if relative_f1 < c.min_improvement_over_champion:
                    failures.append(f"F1 improvement over active champion {relative_f1:.2%} below required {c.min_improvement_over_champion:.2%}")
                if net_delta < c.min_net_expectancy_improvement:
                    failures.append(f"net expectancy improvement over champion {net_delta:.6f} below required {c.min_net_expectancy_improvement:.6f}")
            else:
                failures.append("cannot compare challenger economics with active champion")

            model_results[name] = {
                "passes": not failures,
                "mean_f1": mean_f1,
                "mean_accuracy": mean_accuracy,
                "calibration_score": calibration_score,
                "fold_count": len(folds),
                "failure_reasons": failures,
            }
            reasons.extend(f"{name}: {failure}" for failure in failures)

        if not validation.get("ensemble_passes", False):
            reasons.append("both RF and XGBoost must pass existing walk-forward validation")
        return {
            "passes": not reasons,
            "criteria": {
                "min_samples": c.min_samples, "min_folds": c.min_folds,
                "min_mean_accuracy": c.min_mean_accuracy, "min_mean_f1": c.min_mean_f1,
                "min_net_expectancy": c.min_net_expectancy,
                "max_drawdown_pct": c.max_drawdown_pct,
                "min_calibration_score": c.min_calibration_score,
                "min_stability_score": c.min_stability_score,
                "min_regime_coverage": c.min_regime_coverage,
                "min_improvement_over_champion": c.min_improvement_over_champion,
                "min_net_expectancy_improvement": c.min_net_expectancy_improvement,
            },
            "models": model_results,
            "economic_evidence": economic_by_model,
            "champion_evidence": champion_by_model,
            "failure_reasons": reasons,
            "policy": "fail closed; activation requires every classification, cost-adjusted, calibration, stability, regime and champion comparison check",
        }

    def _calibration_score(self, oof: list[dict[str, Any]]) -> float | None:
        if not oof:
            return None
        errors = []
        for row in oof:
            truth = int(row.get("y_true", -1))
            probabilities = row.get("probabilities")
            if truth not in (0, 1, 2) or not isinstance(probabilities, (list, tuple)) or len(probabilities) != 3:
                return None
            values = [_finite(value) for value in probabilities]
            if any(value is None or value < 0 or value > 1 for value in values):
                return None
            if abs(sum(values) - 1.0) > 1e-3:
                return None
            target = [1.0 if index == truth else 0.0 for index in range(3)]
            errors.append(sum((values[index] - target[index]) ** 2 for index in range(3)))
        brier = sum(errors) / len(errors)
        return 1.0 - brier / 2.0

    def _economic_evidence(
        self, oof: list[dict[str, Any]], metadata: dict[str, Any] | None,
        folds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not oof or not metadata:
            return {"status": "missing", "reason": "OOF predictions or aligned realized-return/cost metadata missing"}
        required = ("timestamps", "actual_return_pct", "transaction_costs", "regimes", "markets", "horizon_minutes")
        if any(key not in metadata for key in required):
            return {"status": "missing", "reason": "required return, costs, market, regime or horizon arrays missing"}
        arrays = {}
        for key in required:
            try:
                arrays[key] = np.asarray(metadata[key]).reshape(-1)
            except Exception:
                return {"status": "missing", "reason": f"invalid metadata {key}"}
        n = len(arrays["actual_return_pct"])
        if any(len(values) != n for values in arrays.values()):
            return {"status": "missing", "reason": "metadata arrays are not aligned"}
        if any(int(row.get("index", -1)) < 0 or int(row["index"]) >= n for row in oof):
            return {"status": "missing", "reason": "OOF index outside aligned metadata"}
        returns = []
        indices = []
        timestamp_returns: dict[int, list[float]] = {}
        regimes: dict[str, list[float]] = {}
        for row in oof:
            index = int(row["index"])
            raw_return = _finite(arrays["actual_return_pct"][index])
            transaction_cost = _finite(arrays["transaction_costs"][index])
            market = str(arrays["markets"][index]).upper()
            regime = str(arrays["regimes"][index]).upper()
            horizon = _finite(arrays["horizon_minutes"][index])
            predicted = int(row.get("y_pred", -1))
            if raw_return is None or transaction_cost is None or transaction_cost < 0 or horizon is None or horizon < 0:
                return {"status": "missing", "reason": "non-finite realized return/cost or invalid horizon"}
            if predicted not in (0, 1, 2) or market not in {"SPOT", "FUTURES"} or regime in {"", "UNKNOWN", "NONE"}:
                return {"status": "missing", "reason": "invalid predicted class, market or unknown regime"}
            direction = 1.0 if predicted == 2 else (-1.0 if predicted == 0 else 0.0)
            gross = (raw_return / 100.0) * direction
            funding = c_funding = 0.0
            if market == "FUTURES" and direction:
                funding = self.criteria.futures_funding_rate_per_8h * int(np.ceil(horizon / 480.0))
            net = gross - transaction_cost - funding
            returns.append(net)
            indices.append(index)
            timestamp = _finite(arrays["timestamps"][index])
            if timestamp is None:
                return {"status": "missing", "reason": "invalid chronological timestamp metadata"}
            timestamp_returns.setdefault(int(timestamp), []).append(net)
            regimes.setdefault(regime, []).append(net)
        if not returns:
            return {"status": "missing", "reason": "no OOF economic samples"}
        equity = peak = 1.0
        max_drawdown = 0.0
        # Aggregate simultaneous symbols into one equal-weight period return.
        period_returns = [sum(values) / len(values) for _, values in sorted(timestamp_returns.items())]
        for net in period_returns:
            equity *= max(0.0, 1.0 + net)
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)
        fold_returns = []
        for fold in folds:
            start, end = fold.get("test_start_index"), fold.get("test_end_index")
            if start is None or end is None:
                continue
            fold_values = [value for value, index in zip(returns, indices) if int(start) <= index <= int(end)]
            if fold_values:
                fold_returns.append(sum(fold_values) / len(fold_values))
        if len(fold_returns) < 2:
            return {"status": "missing", "reason": "insufficient fold net-return evidence for stability"}
        mean_fold = sum(fold_returns) / len(fold_returns)
        std_fold = (sum((value - mean_fold) ** 2 for value in fold_returns) / len(fold_returns)) ** 0.5
        stability = max(0.0, min(1.0, 1.0 - std_fold / max(abs(mean_fold), 1e-6)))
        regime_perf = {
            regime: {"samples": len(values), "net_expectancy": sum(values) / len(values)}
            for regime, values in regimes.items() if len(values) >= self.criteria.min_regime_samples
        }
        coverage = sum(1 for value in regime_perf.values() if value["net_expectancy"] > 0)
        fee_slippage_cost = sum(_finite(arrays["transaction_costs"][index]) or 0.0 for index in indices) / len(indices)
        funding_cost = sum(
            self.criteria.futures_funding_rate_per_8h * int(np.ceil(float(arrays["horizon_minutes"][index]) / 480.0))
            for index in indices if str(arrays["markets"][index]).upper() == "FUTURES"
        ) / len(indices)
        return {
            "status": "ok", "net_expectancy": sum(returns) / len(returns),
            "evaluation_periods": len(period_returns),
            "max_drawdown_pct": max_drawdown, "stability_score": stability,
            "regime_performance": regime_perf, "regime_coverage": coverage,
            "sample_count": len(returns), "mean_fees_and_slippage": fee_slippage_cost,
            "mean_funding_cost": funding_cost,
            "cost_policy": "prediction transaction_costs include round-trip fees and slippage; futures funding estimated at configured rate per 8h interval",
            "fold_net_expectancy": fold_returns,
        }



def _finite(value: Any) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return number if isfinite(number) else None



def calibrate_model_confidence_threshold(predictions: Any, model_version: str, *, min_samples: int = 20) -> dict[str, Any]:
    """Calibrate a model-version-specific live cutoff from resolved historical predictions only.

    Prediction confidence is converted to a directional probability for the
    selector: UP uses confidence, DOWN uses 1-confidence. Actual market return
    remains signed and is never derived from the predicted direction.
    """
    if not model_version:
        return {"status": "model_version_unavailable", "threshold": None, "model_version": None}
    rows = []
    for prediction in predictions:
        if str(getattr(prediction, "model_version", "")) != str(model_version):
            continue
        actual_return = getattr(prediction, "actual_return_pct", None)
        predicted_class = str(getattr(prediction, "predicted_class", "")).upper()
        confidence = _finite(getattr(prediction, "confidence", None))
        if actual_return is None or predicted_class not in {"UP", "DOWN"} or confidence is None:
            continue
        actual_return = _finite(actual_return)
        if actual_return is None or not 0.5 <= confidence <= 1.0:
            continue
        probability_up = confidence if predicted_class == "UP" else 1.0 - confidence
        # DB outcome returns are stored in percentage points (e.g. 1.2 = 1.2%).
        rows.append((probability_up, actual_return / 100.0))
    if len(rows) < min_samples:
        return {
            "status": "insufficient_model_calibration",
            "threshold": None,
            "model_version": model_version,
            "calibration_samples": len(rows),
        }
    result = select_confidence_threshold(
        [row[0] for row in rows],
        [row[1] for row in rows],
        min_trades=min_samples,
    )
    if result.get("status") != "selected_from_historical_calibration":
        return {
            "status": result.get("status", "threshold_unavailable"),
            "threshold": None,
            "model_version": model_version,
            "calibration_samples": len(rows),
        }
    return {
        "status": result["status"],
        "threshold": float(result["threshold"]),
        "model_version": model_version,
        "calibration_samples": len(rows),
        "selected_metrics": result.get("selected_metrics"),
    }


def evaluate_live_confidence(confidence: Any, threshold: Any, model_version: str | None,
                            calibrated_model_version: str | None) -> tuple[bool, str]:
    """Fail-closed live gate; threshold must belong to the exact active model."""
    value = _finite(confidence)
    cutoff = _finite(threshold)
    if not model_version or model_version == "untrained":
        return False, "active_model_unavailable"
    if calibrated_model_version != model_version:
        return False, "model_threshold_version_mismatch"
    if cutoff is None or not 0.5 <= cutoff <= 1.0:
        return False, "calibrated_threshold_unavailable"
    if value is None or not 0.0 <= value <= 1.0:
        return False, "prediction_confidence_unavailable"
    if value < cutoff:
        return False, "below_historical_confidence_threshold"
    return True, "historically_calibrated_confidence_passed"
