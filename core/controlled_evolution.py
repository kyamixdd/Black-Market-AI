"""Human-approved, versioned assistant configuration evolution.

This module never edits source code, installs dependencies, deploys, or executes
proposed actions. Proposals are bounded to validated intelligence settings.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.intelligence_config import (
    IntelligenceConfig,
    get_runtime_intelligence_config,
    save_intelligence_config,
    config_for_mode,
)
from core.runtime_settings_store import SETTINGS_PATH
from benchmarks.assistant_outcomes.evaluate import promotion_gate

EVOLUTION_PATH = SETTINGS_PATH.parent / "controlled_evolution.json"
METRIC_THRESHOLDS = {
    "intent_exact_match": 0.90,
    "tool_registry_safety": 1.0,
    "memory_top1_relevance": 0.80,
    "completion_accuracy": 0.90,
}
ALLOWED_PATCH_FIELDS = {
    "mode", "max_tool_calls", "memory_enabled", "feedback_enabled",
    "provider_enabled", "response_detail",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if not EVOLUTION_PATH.exists():
        return {"schema_version": 1, "proposals": [], "versions": []}
    try:
        state = json.loads(EVOLUTION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Evolution state could not be read safely.") from exc
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise RuntimeError("Evolution state schema is invalid.")
    if not isinstance(state.get("proposals"), list) or not isinstance(state.get("versions"), list):
        raise RuntimeError("Evolution state collections are invalid.")
    return state


def _save_state(state: dict[str, Any]) -> None:
    EVOLUTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".evolution-", suffix=".tmp", dir=EVOLUTION_PATH.parent)
    try:
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError):
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, EVOLUTION_PATH)
        try:
            os.chmod(EVOLUTION_PATH, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def detect_weaknesses(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract measurable failures without changing application behavior."""
    weaknesses: list[dict[str, Any]] = []
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Benchmark report must contain a metrics object.")
    for metric, threshold in METRIC_THRESHOLDS.items():
        value = metrics.get(metric)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            weaknesses.append({"metric": metric, "value": None, "threshold": threshold,
                              "severity": "unknown", "reason": "Metric missing or invalid."})
        elif value < threshold:
            weaknesses.append({"metric": metric, "value": float(value), "threshold": threshold,
                              "severity": "high" if metric == "tool_registry_safety" else "medium",
                              "reason": "Measured value is below the configured benchmark threshold."})
    details = report.get("details", {})
    intent = details.get("intent", []) if isinstance(details, dict) else []
    failed_cases = [item.get("id") for item in intent if isinstance(item, dict) and item.get("pass") is False]
    if failed_cases:
        weaknesses.append({"metric": "intent_case_failures", "failed_case_ids": failed_cases,
                           "severity": "medium", "reason": "Benchmark intent cases did not match expected tools."})
    return weaknesses


def _validate_report_metrics(report: dict[str, Any], label: str) -> None:
    if not isinstance(report, dict) or not isinstance(report.get("metrics"), dict):
        raise ValueError(f"{label.capitalize()} benchmark report must contain metrics.")
    for metric in METRIC_THRESHOLDS:
        value = report["metrics"].get(metric)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
            raise ValueError(f"{label.capitalize()} report metric {metric} must be finite and between 0 and 1.")
    if not isinstance(report.get("report_version"), str) or not report["report_version"]:
        raise ValueError(f"{label.capitalize()} benchmark report version is required.")


def create_improvement_proposal(
    candidate_patch: dict[str, Any],
    candidate_report: dict[str, Any],
    baseline_report: dict[str, Any] | None,
    rationale: str,
) -> dict[str, Any]:
    if not isinstance(candidate_patch, dict) or not candidate_patch:
        raise ValueError("A non-empty configuration patch is required.")
    unknown = set(candidate_patch) - ALLOWED_PATCH_FIELDS
    if unknown:
        raise ValueError("Evolution proposals may only change validated intelligence settings.")
    if not isinstance(rationale, str) or not 10 <= len(rationale.strip()) <= 1000:
        raise ValueError("Proposal rationale must be 10 to 1000 characters.")
    current = get_runtime_intelligence_config()
    if "mode" in candidate_patch:
        values = config_for_mode(candidate_patch["mode"]).model_dump(mode="python")
    else:
        values = current.model_dump(mode="python")
    values.update(candidate_patch)
    candidate_config = IntelligenceConfig.model_validate(values)
    _validate_report_metrics(candidate_report, "candidate")
    if baseline_report is not None:
        _validate_report_metrics(baseline_report, "baseline")
    gate = promotion_gate(candidate_report, baseline_report, {
        "minimum_intent_exact_match": METRIC_THRESHOLDS["intent_exact_match"],
        "minimum_tool_registry_safety": METRIC_THRESHOLDS["tool_registry_safety"],
        "minimum_memory_top1_relevance": METRIC_THRESHOLDS["memory_top1_relevance"],
        "minimum_completion_accuracy": METRIC_THRESHOLDS["completion_accuracy"],
        "no_metric_regression": True,
    })
    proposal = {
        "proposal_id": uuid.uuid4().hex,
        "created_at": _now(),
        "status": "pending_review",
        "rationale": rationale.strip(),
        "patch": candidate_config.model_dump(mode="json"),
        "gate": gate,
        "weaknesses": detect_weaknesses(candidate_report),
        "baseline_report_version": baseline_report.get("report_version") if baseline_report else None,
        "candidate_report_version": candidate_report.get("report_version"),
        "approved_version_id": None,
    }
    state = _load_state()
    state["proposals"].append(proposal)
    _save_state(state)
    return proposal


def list_proposals() -> list[dict[str, Any]]:
    return _load_state()["proposals"]


def approve_proposal(proposal_id: str, *, explicit_approval: bool) -> dict[str, Any]:
    if explicit_approval is not True:
        raise PermissionError("Explicit human approval is required.")
    state = _load_state()
    proposal = next((item for item in state["proposals"] if item["proposal_id"] == proposal_id), None)
    if proposal is None:
        raise KeyError("Proposal not found.")
    if proposal["status"] != "pending_review":
        raise ValueError("Only pending proposals can be approved.")
    if not proposal.get("gate", {}).get("eligible"):
        raise ValueError("Proposal failed validation or regression gates.")
    validated = IntelligenceConfig.model_validate(proposal["patch"])
    version = {
        "version_id": uuid.uuid4().hex,
        "created_at": _now(),
        "source_proposal_id": proposal_id,
        "config": validated.model_dump(mode="json"),
        "previous_config": get_runtime_intelligence_config().model_dump(mode="json"),
    }
    save_intelligence_config(validated)
    state["versions"].append(version)
    proposal["status"] = "approved"
    proposal["approved_version_id"] = version["version_id"]
    _save_state(state)
    return version


def list_versions() -> list[dict[str, Any]]:
    return _load_state()["versions"]


def rollback_version(version_id: str, *, explicit_approval: bool) -> dict[str, Any]:
    if explicit_approval is not True:
        raise PermissionError("Explicit human approval is required for rollback.")
    state = _load_state()
    version = next((item for item in state["versions"] if item["version_id"] == version_id), None)
    if version is None:
        raise KeyError("Version not found.")
    restored = IntelligenceConfig.model_validate(version["previous_config"])
    current = get_runtime_intelligence_config()
    rollback_record = {
        "version_id": uuid.uuid4().hex,
        "created_at": _now(),
        "source_proposal_id": None,
        "rollback_of": version_id,
        "config": restored.model_dump(mode="json"),
        "previous_config": current.model_dump(mode="json"),
    }
    save_intelligence_config(restored)
    state["versions"].append(rollback_record)
    _save_state(state)
    return rollback_record
