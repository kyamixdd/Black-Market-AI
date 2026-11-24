"""Tests for benchmark scoring and promotion safeguards."""
import json
from pathlib import Path

from benchmarks.assistant_outcomes.evaluate import promotion_gate


DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "assistant_outcomes" / "dataset-v1.json"


def test_benchmark_dataset_is_versioned_and_has_required_dimensions():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    assert dataset["version"] == "1.0.0"
    assert dataset["intent_cases"]
    assert dataset["memory_cases"]
    assert dataset["completion_cases"]
    assert dataset["promotion_policy"]["no_metric_regression"] is True


def test_promotion_is_blocked_without_measured_baseline():
    candidate = {"metrics": {
        "intent_exact_match": 1.0, "tool_registry_safety": 1.0,
        "memory_top1_relevance": 1.0, "completion_accuracy": 1.0,
    }}
    decision = promotion_gate(candidate, None, json.loads(DATASET.read_text())["promotion_policy"])
    assert decision["eligible"] is False
    assert "baseline" in decision["reason"].lower()


def test_promotion_requires_thresholds_and_no_regression():
    policy = json.loads(DATASET.read_text())["promotion_policy"]
    baseline = {"metrics": {
        "intent_exact_match": 0.9, "tool_registry_safety": 1.0,
        "memory_top1_relevance": 0.8, "completion_accuracy": 0.9,
    }}
    candidate = {"metrics": dict(baseline["metrics"])}
    assert promotion_gate(candidate, baseline, policy)["eligible"] is True

    candidate["metrics"]["memory_top1_relevance"] = 0.79
    decision = promotion_gate(candidate, baseline, policy)
    assert decision["eligible"] is False
    assert decision["checks"]["memory_top1_relevance"]["no_regression"] is False


def test_promotion_rejects_tool_safety_regression_even_above_other_thresholds():
    policy = json.loads(DATASET.read_text())["promotion_policy"]
    baseline = {"metrics": {
        "intent_exact_match": 0.95, "tool_registry_safety": 1.0,
        "memory_top1_relevance": 0.9, "completion_accuracy": 1.0,
    }}
    candidate = {"metrics": {
        "intent_exact_match": 1.0, "tool_registry_safety": 0.99,
        "memory_top1_relevance": 0.95, "completion_accuracy": 1.0,
    }}
    assert promotion_gate(candidate, baseline, policy)["eligible"] is False
