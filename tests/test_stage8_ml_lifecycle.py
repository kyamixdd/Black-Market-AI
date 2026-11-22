"""Stage 8 validation, calibration and model artifact integrity tests."""
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from learning.model_lifecycle import (
    classification_metrics,
    net_trading_metrics,
    seed_training,
    sha256_file,
    verify_model_artifact,
)


def test_training_is_reproducible_with_explicit_seed():
    rng = np.random.default_rng(19)
    X = rng.normal(size=(180, 5))
    y = (X[:, 0] > 0).astype(int)
    first = RandomForestClassifier(n_estimators=20)
    second = RandomForestClassifier(n_estimators=20)
    seed_training(123, first)
    seed_training(123, second)
    first.fit(X, y)
    second.fit(X, y)
    assert np.array_equal(first.predict(X), second.predict(X))
    assert first.get_params()["random_state"] == 123


def test_classification_metrics_are_held_out_and_calibrated():
    y = np.array([0, 1, 2, 0])
    pred = np.array([0, 1, 1, 0])
    probabilities = np.array([
        [0.8, 0.1, 0.1],
        [0.1, 0.8, 0.1],
        [0.1, 0.7, 0.2],
        [0.7, 0.2, 0.1],
    ])
    result = classification_metrics(y, pred, probabilities)
    assert result["samples"] == 4
    assert result["accuracy"] == 0.75
    assert 0 <= result["brier_score"] <= 2
    assert 0 <= result["expected_calibration_error"] <= 1
    assert result["metric_source"] == "held_out_predictions"


def test_classification_metrics_reject_invalid_probability_rows():
    with pytest.raises(ValueError):
        classification_metrics([0], [0], [[0.2, 0.2, 0.2]])


def test_cost_adjusted_trading_metrics_use_realized_returns():
    result = net_trading_metrics([0.02, -0.01, 0.005], [0.001, 0.001, 0.001])
    assert result["net_expectancy"] == pytest.approx((0.019 - 0.011 + 0.004) / 3)
    assert result["transaction_cost_total"] == pytest.approx(0.003)
    assert result["metric_source"] == "realized_returns_minus_recorded_costs"


def test_artifact_verification_detects_missing_and_tampered_files(tmp_path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"model-artifact-v1")
    digest = sha256_file(artifact)
    assert verify_model_artifact(artifact, digest)[0]
    artifact.write_bytes(b"tampered")
    assert verify_model_artifact(artifact, digest) == (False, "artifact_digest_mismatch")
    assert verify_model_artifact(tmp_path / "missing.bin", digest) == (False, "artifact_missing_or_unreadable")
    assert verify_model_artifact(artifact, "") == (False, "artifact_digest_missing_or_invalid")


def test_trading_metrics_reject_invalid_costs():
    with pytest.raises(ValueError):
        net_trading_metrics([0.01], [-0.001])
