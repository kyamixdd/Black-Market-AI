"""Regression tests for human-gated controlled evolution."""
import json

import pytest

from core import controlled_evolution as evolution
from core.intelligence_config import config_for_mode


@pytest.fixture
def isolated_evolution(tmp_path, monkeypatch):
    state_path = tmp_path / "controlled_evolution.json"
    monkeypatch.setattr(evolution, "EVOLUTION_PATH", state_path)
    current = {"config": config_for_mode("balanced")}
    monkeypatch.setattr(evolution, "get_runtime_intelligence_config", lambda: current["config"])

    def save(config):
        current["config"] = config
        return config

    monkeypatch.setattr(evolution, "save_intelligence_config", save)
    return current, state_path


def report(intent=1.0, safety=1.0, memory=1.0, completion=1.0):
    return {
        "report_version": "1.0.0",
        "metrics": {
            "intent_exact_match": intent,
            "tool_registry_safety": safety,
            "memory_top1_relevance": memory,
            "completion_accuracy": completion,
        },
        "details": {"intent": [{"id": "intent-x", "pass": False}]},
    }


def test_weakness_detection_flags_below_threshold_and_failed_cases():
    weaknesses = evolution.detect_weaknesses(report(intent=0.7, safety=0.9))
    metrics = {item["metric"] for item in weaknesses}
    assert "intent_exact_match" in metrics
    assert "tool_registry_safety" in metrics
    assert "intent_case_failures" in metrics


def test_weakness_detection_rejects_missing_metrics():
    with pytest.raises(ValueError):
        evolution.detect_weaknesses({"details": {}})


def test_proposal_only_accepts_allowlisted_config_fields(isolated_evolution):
    with pytest.raises(ValueError, match="validated intelligence settings"):
        evolution.create_improvement_proposal(
            {"shell_command": "do anything"}, report(), report(),
            "This proposal tries to add an unsafe arbitrary action.",
        )


def test_proposal_without_baseline_cannot_be_approved(isolated_evolution):
    proposal = evolution.create_improvement_proposal(
        {"mode": "fast"}, report(), None,
        "Reduce request cost with a constrained fast profile.",
    )
    assert proposal["status"] == "pending_review"
    assert proposal["gate"]["eligible"] is False
    with pytest.raises(ValueError, match="failed validation"):
        evolution.approve_proposal(proposal["proposal_id"], explicit_approval=True)


def test_approval_requires_explicit_human_confirmation(isolated_evolution):
    proposal = evolution.create_improvement_proposal(
        {"mode": "fast"}, report(), report(),
        "Use a faster mode after passing benchmark gates.",
    )
    with pytest.raises(PermissionError):
        evolution.approve_proposal(proposal["proposal_id"], explicit_approval=False)


def test_approval_versions_config_and_rollback_restores_previous(isolated_evolution):
    current, path = isolated_evolution
    proposal = evolution.create_improvement_proposal(
        {"mode": "fast"}, report(), report(),
        "Use a faster mode after passing benchmark gates.",
    )
    version = evolution.approve_proposal(proposal["proposal_id"], explicit_approval=True)
    assert current["config"].mode.value == "fast"
    assert version["config"]["mode"] == "fast"
    assert version["previous_config"]["mode"] == "balanced"

    rollback = evolution.rollback_version(version["version_id"], explicit_approval=True)
    assert current["config"].mode.value == "balanced"
    assert rollback["rollback_of"] == version["version_id"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert len(stored["versions"]) == 2


def test_rollback_requires_explicit_approval(isolated_evolution):
    proposal = evolution.create_improvement_proposal(
        {"mode": "fast"}, report(), report(),
        "Use a faster mode after passing benchmark gates.",
    )
    version = evolution.approve_proposal(proposal["proposal_id"], explicit_approval=True)
    with pytest.raises(PermissionError):
        evolution.rollback_version(version["version_id"], explicit_approval=False)
