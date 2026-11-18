"""Walk-forward validation for time-series models."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import TimeSeriesSplit

from config import (
    MIN_VALIDATION_ACCURACY,
    MIN_VALIDATION_F1,
    VALIDATION_METRIC,
    WALK_FORWARD_MIN_SAMPLES,
)

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Walk-forward validation for time-ordered data."""

    def __init__(self, n_splits: int = 5, min_train_size: int = WALK_FORWARD_MIN_SAMPLES):
        self.n_splits = n_splits
        self.min_train_size = min_train_size

    def validate(self, X: np.ndarray, y: np.ndarray,
                 model_factory: Any, metric: str | None = None) -> dict[str, Any]:
        """
        Perform walk-forward validation.

        Args:
            X: Feature matrix (time-ordered)
            y: Target vector (time-ordered)
            model_factory: Function returning a fresh model instance
            metric: Metric to optimize ('accuracy', 'f1', 'precision', 'recall'). Defaults to config VALIDATION_METRIC.

        Returns:
            Dict with validation results and metrics
        """
        metric = metric or VALIDATION_METRIC

        if len(X) < self.min_train_size * 2:
            logger.warning("Insufficient data for walk-forward: %d samples", len(X))
            return {"valid": False, "reason": "insufficient_data"}

        tscv = TimeSeriesSplit(n_splits=self.n_splits)
        fold_metrics = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            if len(train_idx) < self.min_train_size:
                continue

            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            # Every fold must learn the complete target vocabulary; otherwise
            # the XGBoost/RF class probability columns cannot be aligned.
            if set(np.unique(y_train).tolist()) != {0, 1, 2}:
                logger.warning("Skipping fold %d: training fold lacks one or more target classes", fold)
                continue

            # Train model. A broken fold invalidates this validation run rather
            # than silently turning a partially evaluated model into a pass.
            model = model_factory()
            model.fit(X_train, y_train)

            # Predict
            y_pred = model.predict(X_test)

            # Calculate metrics
            fold_result = {
                "fold": fold,
                "train_size": len(train_idx),
                "test_size": len(test_idx),
                "accuracy": float(accuracy_score(y_test, y_pred)),
                "precision_macro": float(precision_score(y_test, y_pred, labels=[0, 1, 2], average="macro", zero_division=0)),
                "recall_macro": float(recall_score(y_test, y_pred, labels=[0, 1, 2], average="macro", zero_division=0)),
                "f1_macro": float(f1_score(y_test, y_pred, labels=[0, 1, 2], average="macro", zero_division=0)),
            }
            fold_metrics.append(fold_result)
            logger.debug("Fold %d: acc=%.4f, f1=%.4f", fold, fold_result["accuracy"], fold_result["f1_macro"])

        if not fold_metrics:
            return {"valid": False, "reason": "no_valid_folds"}

        # Aggregate metrics
        avg_metrics = {
            "mean_accuracy": np.mean([m["accuracy"] for m in fold_metrics]),
            "std_accuracy": np.std([m["accuracy"] for m in fold_metrics]),
            "mean_f1": np.mean([m["f1_macro"] for m in fold_metrics]),
            "std_f1": np.std([m["f1_macro"] for m in fold_metrics]),
            "mean_precision": np.mean([m["precision_macro"] for m in fold_metrics]),
            "mean_recall": np.mean([m["recall_macro"] for m in fold_metrics]),
        }

        # Use the metric of interest
        primary_metric = f"mean_{metric}" if metric != "accuracy" else "mean_accuracy"
        primary_value = avg_metrics.get(primary_metric, avg_metrics["mean_accuracy"])

        result = {
            "valid": True,
            "folds": fold_metrics,
            "aggregated": avg_metrics,
            "primary_metric": metric,
            "primary_value": primary_value,
            "passes_threshold": primary_value >= self._get_threshold(metric),
            "min_samples_per_fold": self.min_train_size,
        }

        logger.info("Walk-forward validation: %s=%.4f (threshold=%s), passes=%s",
                    metric, primary_value, self._get_threshold(metric), result["passes_threshold"])
        return result

    def _get_threshold(self, metric: str) -> float:
        """Get minimum threshold for validation metric from config."""
        thresholds = {
            "accuracy": MIN_VALIDATION_ACCURACY,
            "f1": MIN_VALIDATION_F1,
            "precision": MIN_VALIDATION_F1,
            "recall": MIN_VALIDATION_F1,
        }
        return thresholds.get(metric, MIN_VALIDATION_ACCURACY)

    def validate_ensemble(self, X: np.ndarray, y: np.ndarray,
                          rf_params: dict | None = None, xgb_params: dict | None = None) -> dict[str, Any]:
        """Validate both RF and XGBoost, return combined results."""
        rf_params = rf_params or {"n_estimators": 200, "max_depth": 10, "random_state": 42, "n_jobs": 2}
        xgb_params = xgb_params or {"n_estimators": 200, "max_depth": 6, "learning_rate": 0.05,
                                    "random_state": 42, "n_jobs": -1, "eval_metric": "mlogloss"}

        def rf_factory():
            return RandomForestClassifier(**rf_params)

        def xgb_factory():
            return xgb.XGBClassifier(**xgb_params)

        rf_result = self.validate(X, y, rf_factory, "f1")
        xgb_result = self.validate(X, y, xgb_factory, "f1")

        return {
            "rf": rf_result,
            "xgb": xgb_result,
            "ensemble_passes": rf_result.get("passes_threshold", False) and xgb_result.get("passes_threshold", False),
            "recommended_model": "rf" if rf_result.get("primary_value", 0) > xgb_result.get("primary_value", 0) else "xgb",
        }