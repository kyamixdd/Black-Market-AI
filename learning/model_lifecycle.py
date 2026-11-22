"""Validated ML lifecycle utilities: reproducibility, artifact integrity and honest metrics."""
from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def seed_training(seed: int, estimator: Any | None = None) -> int:
    """Set supported RNGs and estimator random_state for repeatable training."""
    value = int(seed)
    random.seed(value)
    np.random.seed(value)
    if estimator is not None and hasattr(estimator, "get_params") and hasattr(estimator, "set_params"):
        params = estimator.get_params(deep=False)
        if "random_state" in params:
            estimator.set_params(random_state=value)
    return value


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Return a streaming SHA-256 digest for a model artifact."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"model artifact missing: {file_path}")
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_artifact(path: str | os.PathLike[str], expected_sha256: str) -> tuple[bool, str]:
    """Fail closed unless the artifact exists and its registry digest matches."""
    if not expected_sha256 or len(expected_sha256) != 64:
        return False, "artifact_digest_missing_or_invalid"
    try:
        actual = sha256_file(path)
    except (OSError, ValueError):
        return False, "artifact_missing_or_unreadable"
    if actual.lower() != expected_sha256.lower():
        return False, "artifact_digest_mismatch"
    return True, actual


def classification_metrics(y_true: Any, y_pred: Any, probabilities: Any) -> dict[str, Any]:
    """Calculate classification and multiclass calibration metrics from held-out predictions."""
    truth = np.asarray(y_true).reshape(-1)
    pred = np.asarray(y_pred).reshape(-1)
    probs = np.asarray(probabilities, dtype=float)
    if truth.size == 0 or truth.shape != pred.shape or probs.shape != (truth.size, 3):
        raise ValueError("held-out labels, predictions and three-class probabilities must align")
    if not np.isin(truth, [0, 1, 2]).all() or not np.isfinite(probs).all():
        raise ValueError("labels must be 0/1/2 and probabilities finite")
    if (probs < 0).any() or (probs > 1).any() or not np.allclose(probs.sum(axis=1), 1.0, atol=1e-5):
        raise ValueError("probability rows must be normalized within [0,1]")
    one_hot = np.eye(3)[truth.astype(int)]
    brier = float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))
    confidence = probs.max(axis=1)
    correct = (pred == truth).astype(float)
    ece = 0.0
    bins = np.linspace(0.0, 1.0, 11)
    for left, right in zip(bins[:-1], bins[1:]):
        mask = (confidence >= left) & (confidence < right if right < 1 else confidence <= right)
        if mask.any():
            ece += float(mask.mean()) * abs(float(correct[mask].mean()) - float(confidence[mask].mean()))
    return {
        "samples": int(truth.size),
        "accuracy": float(accuracy_score(truth, pred)),
        "precision_macro": float(precision_score(truth, pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(truth, pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(truth, pred, average="macro", zero_division=0)),
        "brier_score": brier,
        "expected_calibration_error": float(ece),
        "metric_source": "held_out_predictions",
    }


def net_trading_metrics(realized_returns: Any, transaction_costs: Any) -> dict[str, Any]:
    """Compute trading metrics from aligned realized returns and actual costs (decimal returns)."""
    returns = np.asarray(realized_returns, dtype=float).reshape(-1)
    costs = np.asarray(transaction_costs, dtype=float).reshape(-1)
    if not returns.size or returns.shape != costs.shape:
        raise ValueError("realized returns and costs must be non-empty and aligned")
    if not np.isfinite(returns).all() or not np.isfinite(costs).all() or (costs < 0).any():
        raise ValueError("returns/costs must be finite and costs non-negative")
    net = returns - costs
    equity = np.cumprod(1.0 + net)
    if (equity <= 0).any():
        raise ValueError("net returns imply non-positive equity")
    peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    drawdown = (peaks - equity) / peaks
    gains = float(net[net > 0].sum())
    losses = abs(float(net[net < 0].sum()))
    std = float(net.std(ddof=1)) if len(net) > 1 else 0.0
    return {
        "samples": int(net.size),
        "net_return_pct": float((equity[-1] - 1.0) * 100.0),
        "net_expectancy": float(net.mean()),
        "max_drawdown_pct": float(drawdown.max() * 100.0),
        "profit_factor": gains / losses if losses else (None if gains == 0 else "infinite"),
        "risk_adjusted_performance": float(net.mean() / std * np.sqrt(252.0)) if std > 0 else None,
        "transaction_cost_total": float(costs.sum()),
        "metric_source": "realized_returns_minus_recorded_costs",
    }
