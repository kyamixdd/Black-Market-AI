"""Regression tests for fail-closed model activation."""
import json

from database.connection import Database
from database.repositories import Repository
from learning.trainer import ModelTrainer


def _complete_gate():
    return {
        "passes": True,
        "validation_provenance": {
            "method": "purged_timestamp_walk_forward",
            "out_of_sample": True,
            "timestamps_required": True,
            "purge_gap_ms": 3600000,
            "target_horizon_ms": 3600000,
            "sample_count": 600,
            "rf_oof_count": 180,
            "xgb_oof_count": 180,
        },
        "models": {"rf": {"passes": True}, "xgb": {"passes": True}},
        "economic_evidence": {"rf": {"status": "ok"}, "xgb": {"status": "ok"}},
        "champion_evidence": {"rf": {"status": "ok"}, "xgb": {"status": "ok"}},
    }


def _register_candidate(repo, version, model_type, gate):
    repo.save_model_registry({
        "version": version,
        "model_type": model_type,
        "metrics": json.dumps({"accuracy": 0.99, "scope": "in_sample_diagnostic_only"}),
        "file_path": "candidate-model-artifact",
        "status": "CANDIDATE",
        "is_active": False,
        "is_champion": False,
        "evaluation_data": json.dumps({
            "promotion_gate": gate,
            "training_metrics_in_sample_only": {"accuracy": 0.99},
        }),
    })


def test_repository_rejects_in_sample_metrics_without_oof_gate(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'promotion.db'}")
    db.init_db()
    repo = Repository(db.session_maker())
    try:
        _register_candidate(repo, "rf_candidate", "random_forest", {
            "passes": True,
            "metrics": {"rf_accuracy": 1.0, "rf_f1": 1.0},
        })
        assert repo.promote_model("rf_candidate") is False
        candidate = next(x for x in repo.get_model_registry() if x.version == "rf_candidate")
        assert candidate.is_active is False
        assert candidate.is_champion is False
        assert candidate.status == "CANDIDATE"
    finally:
        db.close()


def test_repository_atomically_promotes_only_candidates_with_complete_gate(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'promotion-valid.db'}")
    db.init_db()
    repo = Repository(db.session_maker())
    try:
        gate = _complete_gate()
        _register_candidate(repo, "rf_candidate", "random_forest", gate)
        _register_candidate(repo, "xgb_candidate", "xgboost", gate)
        assert ModelTrainer._promotion_evidence_passes(gate) is True
        assert repo.promote_models(["rf_candidate", "xgb_candidate"]) is True
        registry = {x.version: x for x in repo.get_model_registry()}
        for version in ("rf_candidate", "xgb_candidate"):
            assert registry[version].is_active is True
            assert registry[version].is_champion is True
            assert registry[version].status == "CHAMPION"
    finally:
        db.close()


def test_promotion_evidence_requires_purge_gap_at_least_target_horizon():
    gate = _complete_gate()
    gate["validation_provenance"]["purge_gap_ms"] = 1000
    assert ModelTrainer._promotion_evidence_passes(gate) is False
