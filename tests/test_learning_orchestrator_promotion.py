"""Regression tests for the legacy learning orchestrator promotion path."""
import pytest

from learning.trainer import LearningOrchestrator


class _Labeler:
    def evaluate_unresolved(self):
        return 0


class _Trainer:
    def __init__(self, result):
        self.result = result

    def retrain_if_needed(self, _predictor):
        return self.result


@pytest.mark.asyncio
async def test_learning_cycle_passes_validation_evidence_to_promotion(monkeypatch):
    validation = {"promotion_gate": {"passes": True, "evidence": "out_of_sample"}}
    orchestrator = LearningOrchestrator(
        repo=object(),
        predictor=object(),
        trainer=_Trainer({"status": "trained", "version": "v2", "validation": validation}),
    )
    monkeypatch.setattr(
        "learning.outcome_labeler.OutcomeLabeler",
        lambda _repo: _Labeler(),
    )
    promoted = []

    async def promote(version, supplied_validation):
        promoted.append((version, supplied_validation))
        return True

    monkeypatch.setattr(orchestrator, "_promote_model", promote)

    result = await orchestrator.run_learning_cycle()

    assert promoted == [("v2", validation)]
    assert result["promoted"] == "v2"
    assert "promotion_blocked" not in result


@pytest.mark.asyncio
async def test_learning_cycle_reports_failed_promotion_without_success_shape(monkeypatch):
    validation = {"promotion_gate": {"passes": True}}
    orchestrator = LearningOrchestrator(
        repo=object(),
        predictor=object(),
        trainer=_Trainer({"status": "trained", "version": "v2", "validation": validation}),
    )
    monkeypatch.setattr(
        "learning.outcome_labeler.OutcomeLabeler",
        lambda _repo: _Labeler(),
    )

    async def promote(_version, _validation):
        return False

    monkeypatch.setattr(orchestrator, "_promote_model", promote)

    result = await orchestrator.run_learning_cycle()

    assert result["promotion_blocked"] == "v2"
    assert "promoted" not in result


@pytest.mark.asyncio
async def test_learning_cycle_does_not_promote_without_gate_evidence(monkeypatch):
    orchestrator = LearningOrchestrator(
        repo=object(),
        predictor=object(),
        trainer=_Trainer({"status": "trained", "version": "v2", "validation": {}}),
    )
    monkeypatch.setattr(
        "learning.outcome_labeler.OutcomeLabeler",
        lambda _repo: _Labeler(),
    )
    calls = []

    async def promote(*args):
        calls.append(args)
        return True

    monkeypatch.setattr(orchestrator, "_promote_model", promote)

    result = await orchestrator.run_learning_cycle()

    assert calls == []
    assert result["promotion_blocked"] == "v2"
