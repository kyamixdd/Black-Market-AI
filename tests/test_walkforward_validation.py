"""Regression tests for chronological and purged walk-forward validation."""
import numpy as np
import pytest
from sklearn.dummy import DummyClassifier

from learning.walkforward_validator import WalkForwardValidator


def dataset(n=120):
    X = np.column_stack((np.arange(n), np.cos(np.arange(n))))
    y = (np.arange(n) % 2).astype(int)
    timestamps = np.arange(n, dtype=np.int64) * 60
    return X, y, timestamps


def test_each_fold_trains_only_on_earlier_rows_and_tests_later():
    X, y, ts = dataset()
    result = WalkForwardValidator(n_splits=4, min_train_size=15, test_size=10).validate(
        X, y, lambda: DummyClassifier(strategy="most_frequent"), timestamps=ts
    )
    assert result["valid"]
    assert len(result["folds"]) == 4
    for fold in result["folds"]:
        assert fold["train_end_index"] < fold["test_start_index"]
        assert fold["train_size"] >= 15
        assert fold["test_end_index"] < len(X)
        assert fold["train_end_time"] < fold["test_start_time"]


def test_label_horizon_purges_overlapping_training_rows():
    X, y, ts = dataset()
    result = WalkForwardValidator(n_splits=3, min_train_size=15, test_size=8).validate(
        X, y, lambda: DummyClassifier(strategy="most_frequent"),
        timestamps=ts, label_horizon=5,
    )
    assert result["valid"]
    for fold in result["folds"]:
        assert fold["purged_samples"] >= 5
        assert fold["test_start_index"] - fold["train_end_index"] - 1 >= 5


def test_rejects_unsorted_or_duplicate_timestamps():
    X, y, ts = dataset()
    ts[25] = ts[24]
    with pytest.raises(ValueError, match="strictly increasing"):
        WalkForwardValidator(n_splits=3, min_train_size=10).validate(
            X, y, lambda: DummyClassifier(), timestamps=ts
        )


def test_rejects_misaligned_features_targets_and_timestamps():
    X, y, ts = dataset()
    with pytest.raises(ValueError, match="aligned"):
        WalkForwardValidator(n_splits=3, min_train_size=10).validate(
            X, y[:-1], lambda: DummyClassifier()
        )
    with pytest.raises(ValueError, match="aligned"):
        WalkForwardValidator(n_splits=3, min_train_size=10).validate(
            X, y, lambda: DummyClassifier(), timestamps=ts[:-1]
        )


def test_insufficient_data_does_not_return_valid_score():
    X, y, ts = dataset(35)
    result = WalkForwardValidator(n_splits=4, min_train_size=20, test_size=5).validate(
        X, y, lambda: DummyClassifier(), timestamps=ts, label_horizon=4
    )
    assert not result["valid"]
    assert result["reason"] == "insufficient_data"



def test_timestamp_purge_uses_elapsed_horizon_with_numeric_boundaries():
    X = np.arange(40, dtype=float).reshape(20, 2)
    y = (np.arange(20) % 2).astype(int)
    ts = np.arange(20, dtype=np.int64) * 60_000
    result = WalkForwardValidator(n_splits=2, min_train_size=4, test_size=2).validate(
        X, y, lambda: DummyClassifier(strategy="most_frequent"),
        timestamps=ts, purge_gap_ms=60_000,
    )
    assert result["valid"]
    for fold in result["folds"]:
        assert fold["train_end_time"] < fold["test_start_time"] - 60_000
        assert isinstance(fold["train_end_time"], (int, np.integer))
        assert isinstance(fold["test_start_time"], (int, np.integer))
