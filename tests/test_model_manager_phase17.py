"""Tests for Phase 17 Champion and Challenger Model Management."""
import tempfile
import os
import json
import joblib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from core.event_bus import EventBus
from database.connection import Database
from database.repositories import Repository
from database.models import ModelRegistryModel
from learning.model_manager import ModelManager, PromotionCriteria, EvaluationResult
from learning.walkforward_validator import WalkForwardValidator


class TestPromotionCriteria:
    """Test promotion criteria configuration."""

    def test_default_criteria(self):
        """Test default promotion criteria values."""
        criteria = PromotionCriteria()
        assert criteria.min_net_expectancy == 0.001
        assert criteria.max_drawdown_pct == 10.0
        assert criteria.min_calibration_score == 0.7
        assert criteria.min_stability_score == 0.6
        assert criteria.min_regime_coverage == 2
        assert criteria.min_samples == 500
        assert criteria.min_improvement_over_champion == 0.02

    def test_custom_criteria(self):
        """Test custom promotion criteria."""
        criteria = PromotionCriteria(
            min_net_expectancy=0.005,
            max_drawdown_pct=5.0,
            min_improvement_over_champion=0.05
        )
        assert criteria.min_net_expectancy == 0.005
        assert criteria.max_drawdown_pct == 5.0
        assert criteria.min_improvement_over_champion == 0.05

    def test_criteria_serialization(self):
        """Test criteria to/from dict."""
        criteria = PromotionCriteria(min_net_expectancy=0.01)
        d = criteria.to_dict()
        assert d["min_net_expectancy"] == 0.01

        criteria2 = PromotionCriteria.from_dict(d)
        assert criteria2.min_net_expectancy == 0.01


class TestModelManager:
    """Test model manager champion/challenger lifecycle."""

    @pytest.fixture
    async def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def repo(self, temp_db):
        session_maker = temp_db.session_maker()
        return Repository(session_maker)

    @pytest.fixture
    def validator(self):
        return WalkForwardValidator(n_splits=3, min_train_size=100)

    @pytest.fixture
    def model_manager(self, repo, validator):
        return ModelManager(repo, validator)

    @pytest.fixture
    def sample_model_file(self):
        """Create a temporary model file."""
        with tempfile.NamedTemporaryFile(suffix='.joblib', delete=False) as f:
            model_path = f.name
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        # Fit on dummy data
        X = np.random.randn(200, 10)
        y = np.random.randint(0, 3, 200)
        model.fit(X, y)
        joblib.dump(model, model_path)
        yield model_path
        os.unlink(model_path)

    @pytest.mark.asyncio
    async def test_register_challenger(self, model_manager, sample_model_file):
        """Test registering a new challenger model."""
        challenger = model_manager.register_challenger(
            version="rf_v1_test",
            model_type="random_forest",
            file_path=sample_model_file,
            metrics={"f1": 0.65, "accuracy": 0.68}
        )

        assert challenger.version == "rf_v1_test"
        assert challenger.model_type == "random_forest"
        assert challenger.status == "CHALLENGER"
        assert challenger.is_champion is False
        assert challenger.rollback_checkpoint is True

    @pytest.mark.asyncio
    async def test_get_challengers(self, model_manager, sample_model_file):
        """Test retrieving challenger models."""
        # Register multiple challengers
        model_manager.register_challenger("rf_v1", "random_forest", sample_model_file, {"f1": 0.6})
        model_manager.register_challenger("rf_v2", "random_forest", sample_model_file, {"f1": 0.65})
        model_manager.register_challenger("xgb_v1", "xgboost", sample_model_file, {"f1": 0.7})

        challengers = model_manager.get_challengers("random_forest")
        assert len(challengers) == 2
        assert all(c.model_type == "random_forest" for c in challengers)

        xgb_challengers = model_manager.get_challengers("xgboost")
        assert len(xgb_challengers) == 1

    @pytest.mark.asyncio
    async def test_evaluate_challenger(self, model_manager, sample_model_file):
        """Test evaluating a challenger against criteria."""
        # Register challenger
        challenger = model_manager.register_challenger(
            "rf_eval_test", "random_forest", sample_model_file, {"f1": 0.6}
        )

        # Create test data
        X = np.random.randn(1000, 10)
        y = np.random.randint(0, 3, 1000)

        # Mock the validator to return good results
        with patch.object(model_manager.validator, 'validate') as mock_validate:
            mock_validate.return_value = {
                "folds": [
                    {"f1_macro": 0.7, "accuracy": 0.72, "train_size": 300, "test_size": 100},
                    {"f1_macro": 0.68, "accuracy": 0.70, "train_size": 300, "test_size": 100},
                    {"f1_macro": 0.72, "accuracy": 0.73, "train_size": 300, "test_size": 100},
                ],
                "aggregated": {"mean_f1": 0.70, "std_f1": 0.02, "mean_accuracy": 0.72}
            }

            result = model_manager.evaluate_challenger(challenger, X, y)

        assert isinstance(result, EvaluationResult)
        assert result.model_version == "rf_eval_test"
        assert result.model_type == "random_forest"
        assert hasattr(result, 'net_expectancy')
        assert hasattr(result, 'max_drawdown_pct')
        assert hasattr(result, 'passes_criteria')

    @pytest.mark.asyncio
    async def test_challenger_fails_criteria(self, model_manager, sample_model_file):
        """Test challenger that fails promotion criteria."""
        challenger = model_manager.register_challenger(
            "rf_bad", "random_forest", sample_model_file, {"f1": 0.4}
        )

        X = np.random.randn(1000, 10)
        y = np.random.randint(0, 3, 1000)

        # Mock validator to return poor results
        with patch.object(model_manager.validator, 'validate') as mock_validate:
            mock_validate.return_value = {
                "folds": [
                    {"f1_macro": 0.3, "accuracy": 0.35, "train_size": 300, "test_size": 100},
                    {"f1_macro": 0.28, "accuracy": 0.32, "train_size": 300, "test_size": 100},
                    {"f1_macro": 0.32, "accuracy": 0.36, "train_size": 300, "test_size": 100},
                ],
                "aggregated": {"mean_f1": 0.30, "std_f1": 0.02, "mean_accuracy": 0.35}
            }

            result = model_manager.evaluate_challenger(challenger, X, y)

        assert result.passes_criteria is False
        assert len(result.failure_reasons) > 0

    @pytest.mark.asyncio
    async def test_get_champion_no_champion(self, model_manager):
        """Test getting champion when none exists."""
        champion = model_manager.get_champion("random_forest")
        assert champion is None

    @pytest.mark.asyncio
    async def test_promote_challenger_fails_without_criteria(self, model_manager, sample_model_file):
        """Test promotion fails when criteria not met."""
        challenger = model_manager.register_challenger(
            "rf_promote_fail", "random_forest", sample_model_file, {"f1": 0.6}
        )

        # Create failed evaluation
        eval_result = EvaluationResult(
            model_version="rf_promote_fail",
            model_type="random_forest",
            net_expectancy=-0.01,  # Negative!
            max_drawdown_pct=15.0,  # Too high!
            calibration_score=0.5,
            stability_score=0.4,
            regime_performance={},
            total_samples=500,
            primary_metric="f1",
            primary_value=0.5,
            passes_criteria=False,
            failure_reasons=["Net expectancy negative", "Drawdown too high"]
        )

        success = model_manager.promote_challenger("rf_promote_fail", eval_result)
        assert success is False

    @pytest.mark.asyncio
    async def test_model_history(self, model_manager, sample_model_file):
        """Test getting model history."""
        model_manager.register_challenger("rf_v1", "random_forest", sample_model_file, {"f1": 0.6})
        model_manager.register_challenger("rf_v2", "random_forest", sample_model_file, {"f1": 0.65})
        model_manager.register_challenger("xgb_v1", "xgboost", sample_model_file, {"f1": 0.7})

        history = model_manager.get_model_history("random_forest")
        assert len(history) == 2
        assert all(m.model_type == "random_forest" for m in history)

        xgb_history = model_manager.get_model_history("xgboost")
        assert len(xgb_history) == 1


class TestModelManagerIntegration:
    """Integration tests for model manager with real components."""

    @pytest.fixture
    async def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def repo(self, temp_db):
        session_maker = temp_db.session_maker()
        return Repository(session_maker)

    @pytest.mark.asyncio
    async def test_champion_promotion_flow(self, repo):
        """Test full champion promotion flow."""
        validator = WalkForwardValidator(n_splits=3, min_train_size=100)
        manager = ModelManager(repo, validator)

        # Create models
        with tempfile.NamedTemporaryFile(suffix='.joblib', delete=False) as f:
            champ_path = f.name
        with tempfile.NamedTemporaryFile(suffix='.joblib', delete=False) as f:
            chal_path = f.name

        try:
            champ_model = RandomForestClassifier(n_estimators=20, random_state=42)
            chal_model = RandomForestClassifier(n_estimators=30, random_state=42)

            X_train = np.random.randn(300, 10)
            y_train = np.random.randint(0, 3, 300)
            champ_model.fit(X_train, y_train)
            chal_model.fit(X_train, y_train)

            joblib.dump(champ_model, champ_path)
            joblib.dump(chal_model, chal_path)

            # Register and promote champion
            champion = ModelRegistryModel(
                version="rf_champion_v1",
                model_type="random_forest",
                file_path=champ_path,
                metrics=json.dumps({"f1": 0.72}),
                status="CHAMPION",
                is_active=True,
                is_champion=True,
                rollback_checkpoint=True
            )
            repo.save_model_registry({
                "version": champion.version,
                "model_type": champion.model_type,
                "file_path": champion.file_path,
                "metrics": champion.metrics,
                "status": champion.status,
                "is_active": champion.is_active,
                "is_champion": champion.is_champion,
                "rollback_checkpoint": champion.rollback_checkpoint
            })

            # Register challenger
            challenger = manager.register_challenger(
                "rf_challenger_v1", "random_forest", chal_path, {"f1": 0.75}
            )

            # Verify both exist
            champ = manager.get_champion("random_forest")
            assert champ is not None
            assert champ.version == "rf_champion_v1"

            challengers = manager.get_challengers("random_forest")
            assert len(challengers) == 1
            assert challengers[0].version == "rf_challenger_v1"

        finally:
            os.unlink(champ_path)
            os.unlink(chal_path)


class TestEvaluationResult:
    """Test evaluation result dataclass."""

    def test_evaluation_result_creation(self):
        """Test creating evaluation result."""
        result = EvaluationResult(
            model_version="test_v1",
            model_type="random_forest",
            net_expectancy=0.02,
            max_drawdown_pct=5.0,
            calibration_score=0.8,
            stability_score=0.7,
            regime_performance={"BULL": 0.75, "BEAR": 0.65},
            total_samples=1000,
            primary_metric="f1",
            primary_value=0.72,
            passes_criteria=True,
            failure_reasons=[]
        )

        assert result.model_version == "test_v1"
        assert result.passes_criteria is True
        assert result.net_expectancy == 0.02
        assert len(result.regime_performance) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])