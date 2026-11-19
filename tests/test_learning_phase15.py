"""Tests for Phase 15 Self-Evaluation and Prediction Accountability."""
import json
import tempfile
import os
from datetime import datetime, timezone, timedelta
import pytest

from core.event_bus import EventBus
from database.connection import Database
from database.repositories import Repository
from database.models import PredictionModel
from learning.outcome_labeler import OutcomeLabeler
from learning.performance_analyzer import PerformanceAnalyzer
from paper_trading.simulator import Simulator


class TestOutcomeLabeler:
    """Test outcome labeling and evaluation."""

    @pytest.fixture
    async def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_outcome_labeler_initialization(self, temp_db):
        """Test OutcomeLabeler initializes with repo and simulator."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        sim = Simulator(EventBus())
        labeler = OutcomeLabeler(repo, sim)
        assert labeler.repo is repo
        assert labeler.simulator is sim

    @pytest.mark.asyncio
    async def test_evaluate_unresolved_no_data(self, temp_db):
        """Test evaluate_unresolved returns 0 when no predictions."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        sim = Simulator(EventBus())
        labeler = OutcomeLabeler(repo, sim)
        count = labeler.evaluate_unresolved()
        assert count == 0

    @pytest.mark.asyncio
    async def test_evaluate_unresolved_horizon_not_reached(self, temp_db):
        """Test predictions with unexpired horizon are not evaluated."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        sim = Simulator(EventBus())
        labeler = OutcomeLabeler(repo, sim)

        # Create a prediction with future horizon (not ready)
        pred_id = "PRED-TEST-001"
        repo.save_prediction({
            "prediction_id": pred_id,
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "model_version": "test_v1",
            "horizon_minutes": 60,
            "prob_up": 0.6,
            "prob_down": 0.2,
            "prob_flat": 0.2,
            "predicted_class": "UP",
            "confidence": 0.8,
            "created_at": datetime.now(timezone.utc),
        })

        count = labeler.evaluate_unresolved()
        assert count == 0  # Not evaluated yet

        # Verify prediction is still unresolved
        unresolved = repo.get_unresolved_predictions()
        assert len(unresolved) == 1


class TestPerformanceAnalyzer:
    """Test performance analysis and improvement proposals."""

    @pytest.fixture
    async def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_performance_analyzer_initialization(self, temp_db):
        """Test PerformanceAnalyzer initializes."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        analyzer = PerformanceAnalyzer(repo)
        assert analyzer.repo is repo

    @pytest.mark.asyncio
    async def test_generate_report_insufficient_data(self, temp_db):
        """Test generate_report handles no data gracefully."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        analyzer = PerformanceAnalyzer(repo)
        report = analyzer.generate_report(days=7)
        assert report["status"] == "insufficient_data"

    @pytest.mark.asyncio
    async def test_generate_report_with_data(self, temp_db):
        """Test generate_report calculates metrics correctly."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        analyzer = PerformanceAnalyzer(repo)

        # Create evaluated predictions
        for i in range(10):
            pred_id = f"PRED-REPORT-{i}"
            repo.save_prediction({
                "prediction_id": pred_id,
                "symbol": "BTCUSDT" if i < 5 else "ETHUSDT",
                "market": "SPOT",
                "model_version": "test_v1",
                "strategy_version": "momentum",
                "timeframe": "1h",
                "regime": "BULL_TREND",
                "horizon_minutes": 60,
                "prob_up": 0.6,
                "prob_down": 0.2,
                "prob_flat": 0.2,
                "predicted_class": "UP",
                "confidence": 0.8,
                "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
                "eval_time": datetime.now(timezone.utc) - timedelta(hours=1),
                "actual_outcome": "UP" if i < 7 else "DOWN",
                "actual_return_pct": 1.5 if i < 7 else -0.5,
                "is_correct": True if i < 7 else False,
                "simulated_pnl": 0.015 if i < 7 else -0.005,
                "transaction_costs": 0.001,
            })

        report = analyzer.generate_report(days=1)
        assert "total_predictions" in report
        assert report["total_predictions"] == 10
        assert report["accuracy"] == 0.7
        assert report["correct_predictions"] == 7
        assert "by_strategy" in report
        assert "by_market" in report
        assert "by_symbol" in report
        assert "by_timeframe" in report
        assert "by_regime" in report
        assert "by_model_version" in report
        assert "by_confidence_range" in report
        assert "improvement_proposals" in report

    @pytest.mark.asyncio
    async def test_failure_pattern_detection(self, temp_db):
        """Test failure pattern detection identifies weak strategies."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        analyzer = PerformanceAnalyzer(repo)

        # Create predictions with a failing strategy (low accuracy)
        for i in range(20):
            pred_id = f"PRED-FAIL-{i}"
            repo.save_prediction({
                "prediction_id": pred_id,
                "symbol": "BTCUSDT",
                "market": "SPOT",
                "model_version": "test_v1",
                "strategy_version": "bad_strategy",
                "timeframe": "1h",
                "regime": "SIDEWAYS",
                "horizon_minutes": 60,
                "prob_up": 0.5,
                "prob_down": 0.3,
                "prob_flat": 0.2,
                "predicted_class": "UP",
                "confidence": 0.6,
                "created_at": datetime.now(timezone.utc) - timedelta(hours=3),
                "eval_time": datetime.now(timezone.utc) - timedelta(hours=2),
                "actual_outcome": "UP" if i < 5 else "DOWN",  # 25% accuracy
                "actual_return_pct": 1.0 if i < 5 else -0.5,
                "is_correct": True if i < 5 else False,
                "simulated_pnl": 0.01 if i < 5 else -0.005,
                "transaction_costs": 0.001,
            })

        report = analyzer.generate_report(days=1)
        # Should detect strategy failure
        failure_patterns = report.get("failure_patterns", [])
        assert len(failure_patterns) > 0
        strat_failures = [f for f in failure_patterns if f["type"] == "strategy_failure"]
        assert len(strat_failures) > 0
        assert strat_failures[0]["value"] == "bad_strategy"

        # Should generate improvement proposal
        proposals = report.get("improvement_proposals", [])
        assert len(proposals) > 0
        # Should have a strategy weight adjustment proposal
        weight_props = [p for p in proposals if p["category"] == "Strategy Weight Adjustment"]
        assert len(weight_props) > 0

    @pytest.mark.asyncio
    async def test_confidence_miscalibration_detection(self, temp_db):
        """Test detection of high-confidence incorrect predictions."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        analyzer = PerformanceAnalyzer(repo)

        # Create many high-confidence wrong predictions
        for i in range(10):
            pred_id = f"PRED-MISCAL-{i}"
            repo.save_prediction({
                "prediction_id": pred_id,
                "symbol": "BTCUSDT",
                "market": "SPOT",
                "model_version": "test_v1",
                "strategy_version": "momentum",
                "timeframe": "1h",
                "regime": "BULL_TREND",
                "horizon_minutes": 60,
                "prob_up": 0.9,
                "prob_down": 0.05,
                "prob_flat": 0.05,
                "predicted_class": "UP",
                "confidence": 0.9,  # Very high confidence
                "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
                "eval_time": datetime.now(timezone.utc) - timedelta(hours=1),
                "actual_outcome": "DOWN",  # Wrong!
                "actual_return_pct": -1.0,
                "is_correct": False,
                "simulated_pnl": -0.01,
                "transaction_costs": 0.001,
            })

        report = analyzer.generate_report(days=1)
        failure_patterns = report.get("failure_patterns", [])
        cal_patterns = [f for f in failure_patterns if f["type"] == "confidence_miscalibration"]
        assert len(cal_patterns) > 0

        # Should propose confidence recalibration
        proposals = report.get("improvement_proposals", [])
        cal_props = [p for p in proposals if p["category"] == "Confidence Calibration"]
        assert len(cal_props) > 0


class TestPredictionStorage:
    """Test enhanced prediction storage with all required fields."""

    @pytest.fixture
    async def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_prediction_storage_with_new_fields(self, temp_db):
        """Test that PredictionModel accepts all new accountability fields."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)

        pred_data = {
            "prediction_id": "PRED-NEWFIELDS-001",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "timeframe": "1h",
            "model_version": "rf_v2",
            "strategy_version": "momentum",
            "regime": "BULL_TREND",
            "horizon_minutes": 60,
            "prob_up": 0.6,
            "prob_down": 0.2,
            "prob_flat": 0.2,
            "predicted_class": "UP",
            "confidence": 0.75,
            "feature_values": json.dumps({"rsi": 65, "macd": 0.02, "adx": 30}),
            "created_at": datetime.now(timezone.utc),
        }

        repo.save_prediction(pred_data)

        # Verify retrieval
        history = repo.get_predictions_history(limit=10)
        assert len(history) == 1
        p = history[0]
        assert p.timeframe == "1h"
        assert p.strategy_version == "momentum"
        assert p.regime == "BULL_TREND"
        assert p.feature_values is not None
        # Verify it's valid JSON
        features = json.loads(p.feature_values)
        assert features["rsi"] == 65


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

@pytest.mark.asyncio
async def test_learning_cycle_keeps_new_classifier_candidate_inactive(monkeypatch):
    from learning.outcome_labeler import OutcomeLabeler
    from learning.trainer import LearningOrchestrator

    class FakeTrainer:
        def retrain_if_needed(self, _predictor):
            return {
                "status": "trained",
                "version": "candidate-001",
                "validation": {"ensemble_passes": True},
            }

    monkeypatch.setattr(OutcomeLabeler, "evaluate_unresolved", lambda self: 2)
    learning = LearningOrchestrator(repo=object(), predictor=object(), trainer=FakeTrainer())

    result = await learning.run_learning_cycle()

    assert result["outcomes_labeled"] == 2
    assert result["retrain"]["status"] == "trained"
    assert result["promotion"]["status"] == "deferred"
    assert result["promotion"]["active_model_unchanged"] is True
    assert "promoted" not in result


def test_model_trainer_does_not_accept_candidate_without_river_artifact(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from learning import trainer as trainer_module

    monkeypatch.setattr(trainer_module, "MODELS_DIR", str(tmp_path))
    trainer = trainer_module.ModelTrainer(repo=object(), dataset_builder=SimpleNamespace())
    (tmp_path / "rf_candidate.pkl").write_bytes(b"rf")
    (tmp_path / "xgb_candidate.json").write_text("{}", encoding="utf-8")
    (tmp_path / "scaler_candidate.pkl").write_bytes(b"scaler")

    with pytest.raises(FileNotFoundError, match="required artifacts"):
        trainer.activate_version("candidate")


def test_trainer_waits_for_economic_review_instead_of_retraining_pending_candidate(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from learning import trainer as trainer_module

    monkeypatch.setattr(trainer_module, "MODELS_DIR", str(tmp_path / "models"))
    db = Database(f"sqlite:///{tmp_path / 'learning-candidate.db'}")
    db.init_db()
    repo = Repository(db.session_maker())
    repo.save_model_registry({
        "version": "random_forest_candidate-001",
        "model_type": "random_forest",
        "metrics": {"accuracy": 0.8},
        "file_path": str(tmp_path / "models" / "rf_candidate-001.pkl"),
        "status": "VALIDATED",
        "is_active": False,
    })
    trainer = trainer_module.ModelTrainer(repo=repo, dataset_builder=SimpleNamespace())
    training_calls = []
    trainer.train_and_validate = lambda: training_calls.append(True)

    try:
        result = trainer.retrain_if_needed(object())
        assert result["status"] == "candidate_pending_review"
        assert result["candidate"] == "random_forest_candidate-001"
        assert training_calls == []
    finally:
        db.close()
