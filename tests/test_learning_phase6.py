"""Test Phase 6 Hybrid Local Learning Engine."""
import os
import tempfile

import numpy as np
import pytest

from database.connection import Database
from database.repositories import Repository
from learning.dataset_builder import DatasetBuilder
from learning.feature_engine import FeatureEngine
from learning.outcome_labeler import OutcomeLabeler
from learning.predictor import Predictor
from learning.trainer import ModelTrainer
from learning.walkforward_validator import WalkForwardValidator


class TestFeatureEngine:
    """Test feature engineering for learning."""

    def test_feature_engine_imports(self):
        engine = FeatureEngine()
        assert engine is not None

    def test_build_features_shape(self):
        engine = FeatureEngine()
        # Create dummy OHLC data
        ohlc = {
            "15m": {
                "open": np.random.rand(50).astype(np.float32) * 1000,
                "high": np.random.rand(50).astype(np.float32) * 1000 + 10,
                "low": np.random.rand(50).astype(np.float32) * 1000 - 10,
                "close": np.random.rand(50).astype(np.float32) * 1000,
                "volume": np.random.rand(50).astype(np.float32) * 10000,
            }
        }
        features = engine.build_features("BTCUSDT", "SPOT", ohlc)
        assert isinstance(features, np.ndarray)
        assert features.shape[0] > 0


class TestPredictor:
    """Test predictor with untrained model fallback."""

    def test_predictor_untrained_fallback(self):
        pred = Predictor()
        features = np.random.rand(48).astype(np.float32)
        result = pred.predict(features)

        assert "prob_up" in result
        assert "prob_down" in result
        assert "prob_flat" in result
        assert "predicted_class" in result
        assert "confidence" in result
        assert "model_version" in result
        # Untrained model returns low confidence
        assert result["confidence"] == 0.0


class TestWalkForwardValidator:
    """Test walk-forward validation."""

    def test_validator_insufficient_data(self):
        validator = WalkForwardValidator(min_train_size=100)
        X = np.random.rand(50, 10).astype(np.float32)
        y = np.random.randint(0, 3, 50).astype(np.int32)
        result = validator.validate(X, y, lambda: None)
        assert result["valid"] is False
        assert result["reason"] == "insufficient_data"

    def test_validator_rf(self):
        validator = WalkForwardValidator(n_splits=3, min_train_size=100)
        X = np.random.rand(300, 10).astype(np.float32)
        y = np.random.randint(0, 3, 300).astype(np.int32)

        from sklearn.ensemble import RandomForestClassifier
        result = validator.validate(X, y, lambda: RandomForestClassifier(n_estimators=50, random_state=42))

        # With random data, it may or may not pass threshold
        assert "valid" in result
        assert "folds" in result
        assert "aggregated" in result

    def test_validator_ensemble(self):
        validator = WalkForwardValidator(n_splits=3, min_train_size=100)
        X = np.random.rand(300, 10).astype(np.float32)
        y = np.random.randint(0, 3, 300).astype(np.int32)

        result = validator.validate_ensemble(X, y)

        assert "rf" in result
        assert "xgb" in result
        assert "ensemble_passes" in result
        assert "recommended_model" in result


class TestDatasetBuilder:
    """Test dataset builder."""

    def test_dataset_builder_init(self):
        # Use temp database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            db = Database(f"sqlite:///{db_path}")
            db.init_db()
            session_maker = db.session_maker()
            repo = Repository(session_maker)
            builder = DatasetBuilder(repo)
            assert builder is not None
        finally:
            db.close()
            os.unlink(db_path)

    def test_outcome_to_class(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            db = Database(f"sqlite:///{db_path}")
            db.init_db()
            session_maker = db.session_maker()
            repo = Repository(session_maker)
            builder = DatasetBuilder(repo)
            assert builder._outcome_to_class("UP") == 2
            assert builder._outcome_to_class("DOWN") == 0
            assert builder._outcome_to_class("FLAT") == 1
            assert builder._outcome_to_class("UNKNOWN") == 1
        finally:
            db.close()
            os.unlink(db_path)


class TestOutcomeLabeler:
    """Test outcome labeling."""

    def test_labeler_init(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            db = Database(f"sqlite:///{db_path}")
            db.init_db()
            session_maker = db.session_maker()
            repo = Repository(session_maker)
            labeler = OutcomeLabeler(repo)
            assert labeler is not None
            assert labeler.horizon_minutes == 60
        finally:
            db.close()
            os.unlink(db_path)


class TestModelTrainer:
    """Test model trainer."""

    def test_trainer_init(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            db = Database(f"sqlite:///{db_path}")
            db.init_db()
            session_maker = db.session_maker()
            repo = Repository(session_maker)
            trainer = ModelTrainer(repo)
            assert trainer is not None
            assert trainer.model_dir.exists()
        finally:
            db.close()
            os.unlink(db_path)


class TestLearningIntegration:
    """Integration tests for learning components."""

    def test_full_training_pipeline_with_synthetic_data(self):
        """Test the full pipeline with synthetic data."""
        import xgboost as xgb
        from sklearn.ensemble import RandomForestClassifier

        # Create a synthetic dataset with some pattern (all 3 classes)
        np.random.seed(42)
        n_samples = 1000
        X = np.random.rand(n_samples, 10).astype(np.float32)
        # Create pattern with 3 classes: feature 0 determines class
        # < 0.33 -> DOWN (0), 0.33-0.66 -> FLAT (1), > 0.66 -> UP (2)
        y = np.where(X[:, 0] < 0.33, 0, np.where(X[:, 0] < 0.66, 1, 2)).astype(np.int32)

        # Walk-forward validation
        validator = WalkForwardValidator(n_splits=3, min_train_size=100)
        result = validator.validate_ensemble(X, y)

        # Should pass with this clear pattern
        assert result["rf"]["valid"] is True
        assert result["xgb"]["valid"] is True
        assert result["rf"]["primary_value"] > 0.6
        assert result["xgb"]["primary_value"] > 0.6

        # Test training on full dataset
        rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        rf.fit(X, y)
        rf_score = rf.score(X, y)
        assert rf_score > 0.7

        xgb_model = xgb.XGBClassifier(n_estimators=100, random_state=42, n_jobs=-1, eval_metric="mlogloss")
        xgb_model.fit(X, y)
        xgb_score = xgb_model.score(X, y)
        assert xgb_score > 0.7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])