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

    def __init__(
        self, n_splits: int = 5,
        min_train_size: int = WALK_FORWARD_MIN_SAMPLES,
        test_size: int | None = None,
        gap: int = 0,
        max_train_size: int | None = None,
    ):
        if n_splits < 1 or min_train_size < 1 or gap < 0:
            raise ValueError("n_splits/min_train_size must be positive and gap non-negative")
        self.n_splits = n_splits
        self.min_train_size = min_train_size
        self.test_size = test_size
        self.gap = gap
        self.max_train_size = max_train_size

    def validate(
        self, X: np.ndarray, y: np.ndarray, model_factory: Any,
        metric: str | None = None, timestamps: Any = None,
        gap: int | None = None, label_horizon: int = 0,
        test_size: int | None = None,
    ) -> dict[str, Any]:
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
        metric = (metric or VALIDATION_METRIC).lower()
        X = np.asarray(X)
        y = np.asarray(y)
        if X.ndim != 2 or y.ndim != 1 or len(X) != len(y):
            raise ValueError("X must be 2D and y must be a 1D aligned target")
        if label_horizon < 0:
            raise ValueError("label_horizon cannot be negative")
        effective_gap = max(self.gap if gap is None else gap, label_horizon)
        if effective_gap < 0:
            raise ValueError("gap cannot be negative")
        time_values = None
        if timestamps is not None:
            time_values = np.asarray(timestamps)
            if time_values.ndim != 1 or len(time_values) != len(X):
                raise ValueError("timestamps must be a 1D array aligned with X and y")
            normalized = []
            for value in time_values:
                if isinstance(value, np.datetime64):
                    if np.isnat(value):
                        raise ValueError("timestamps cannot contain NaT")
                    value = value.astype("datetime64[ns]").astype(np.int64)
                elif hasattr(value, "timestamp") and callable(value.timestamp):
                    value = value.timestamp()
                normalized.append(value)
            try:
                if any(normalized[i] >= normalized[i + 1] for i in range(len(normalized)-1)):
                    raise ValueError("timestamps must be strictly increasing")
            except TypeError as exc:
                raise ValueError("timestamps must have a comparable type") from exc

        if len(X) < self.min_train_size * 2:
            logger.warning("Insufficient data for walk-forward: %d samples", len(X))
            return {"valid": False, "reason": "insufficient_data"}

        fold_test_size = test_size if test_size is not None else self.test_size
        tscv = TimeSeriesSplit(
            n_splits=self.n_splits,
            test_size=fold_test_size,
            max_train_size=self.max_train_size,
            gap=effective_gap,
        )
        fold_metrics = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            if len(train_idx) < self.min_train_size:
                continue

            if train_idx[-1] >= test_idx[0]:
                raise RuntimeError("walk-forward training overlaps the future test window")
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # Train model
            model = model_factory()
            model.fit(X_train, y_train)

            # Predict
            y_pred = model.predict(X_test)

            # Calculate metrics
            fold_result = {
                "fold": fold,
                "train_size": len(train_idx),
                "test_size": len(test_idx),
                "train_start_index": int(train_idx[0]),
                "train_end_index": int(train_idx[-1]),
                "test_start_index": int(test_idx[0]),
                "test_end_index": int(test_idx[-1]),
                "purged_samples": int(test_idx[0] - train_idx[-1] - 1),
                "accuracy": float(accuracy_score(y_test, y_pred)),
                "precision_macro": float(precision_score(y_test, y_pred, average="macro", zero_division=0)),
                "recall_macro": float(recall_score(y_test, y_pred, average="macro", zero_division=0)),
                "f1_macro": float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
            }
            if time_values is not None:
                fold_result.update({
                    "train_start_time": str(time_values[train_idx[0]]),
                    "train_end_time": str(time_values[train_idx[-1]]),
                    "test_start_time": str(time_values[test_idx[0]]),
                    "test_end_time": str(time_values[test_idx[-1]]),
                })
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
        rf_params = rf_params or {"n_estimators": 100, "max_depth": 10, "random_state": 42, "n_jobs": -1}
        xgb_params = xgb_params or {"n_estimators": 100, "max_depth": 6, "learning_rate": 0.05,
                                    "random_state": 42, "n_jobs": 1, "eval_metric": "mlogloss"}

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
