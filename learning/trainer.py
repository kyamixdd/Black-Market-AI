"""Model trainer: trains RF, XGBoost, and River online models with validation."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import xgboost as xgb
from river import compose, preprocessing, tree
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from config import MODELS_DIR
from database.repositories import Repository
from learning.dataset_builder import DatasetBuilder
from learning.predictor import Predictor
from learning.walkforward_validator import WalkForwardValidator

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Trains and validates ML models for the hybrid learning engine."""

    def __init__(self, repo: Repository, dataset_builder: DatasetBuilder | None = None):
        self.repo = repo
        self.dataset_builder = dataset_builder or DatasetBuilder(repo)
        self.validator = WalkForwardValidator()
        self.model_dir = Path(MODELS_DIR)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def train_and_validate(self) -> dict[str, Any]:
        """Full training pipeline: build dataset, validate, train, register."""
        # 1. Build dataset
        X, y = self.dataset_builder.build_dataset()
        if len(X) == 0:
            return {"status": "insufficient_data", "samples": 0}
        if X.ndim != 2 or not np.isfinite(X).all():
            return {"status": "invalid_dataset", "samples": int(len(X))}
        class_counts = {int(label): int(count) for label, count in zip(*np.unique(y, return_counts=True))}
        if set(class_counts) != {0, 1, 2}:
            return {
                "status": "insufficient_class_diversity",
                "samples": int(len(X)),
                "class_counts": class_counts,
                "required_classes": [0, 1, 2],
            }

        # 2. Walk-forward validation
        validation = self.validator.validate_ensemble(X, y)
        logger.info("Validation complete: RF passes=%s, XGB passes=%s",
                    validation["rf"].get("passes_threshold", False),
                    validation["xgb"].get("passes_threshold", False))

        # 3. If validation passes, train final models on full dataset
        if validation["ensemble_passes"]:
            version = self._generate_version()
            train_result = self._train_final_models(X, y, version)
            train_result["validation"] = validation
            train_result["version"] = version
            train_result["status"] = "trained"
            return train_result
        else:
            # Still save validation results for analysis
            version = self._generate_version()
            self._save_validation_record(version, validation)
            return {
                "status": "validation_failed",
                "version": version,
                "validation": validation,
                "samples": len(X),
            }

    def _train_final_models(self, X: np.ndarray, y: np.ndarray, version: str) -> dict[str, Any]:
        """Train final models on full dataset and save."""
        # Train RF
        rf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=2)
        rf.fit(X, y)

        # Train XGBoost
        xgb_model = xgb.XGBClassifier(
            n_estimators=200, max_depth=8, learning_rate=0.05,
            random_state=42, n_jobs=2, eval_metric="mlogloss"
        )
        xgb_model.fit(X, y)

        # Fit scaler
        scaler = StandardScaler()
        scaler.fit(X)

        # Save models
        rf_path = self.model_dir / f"rf_{version}.pkl"
        xgb_path = self.model_dir / f"xgb_{version}.json"
        scaler_path = self.model_dir / f"scaler_{version}.pkl"

        joblib.dump(rf, rf_path)
        xgb_model.save_model(str(xgb_path))
        joblib.dump(scaler, scaler_path)

        # Train the online River model as the incremental-learning leg of the hybrid.
        self.train_river_online(X, y, version=version)

        # Update portable "latest" model copies after all artifacts are written.
        self._update_latest_symlinks(version)

        # Calculate training metrics
        rf_pred = rf.predict(X)
        xgb_pred = xgb_model.predict(X)
        from sklearn.metrics import accuracy_score, f1_score
        metrics = {
            "rf_accuracy": float(accuracy_score(y, rf_pred)),
            "xgb_accuracy": float(accuracy_score(y, xgb_pred)),
            "rf_f1": float(f1_score(y, rf_pred, average="macro", zero_division=0)),
            "xgb_f1": float(f1_score(y, xgb_pred, average="macro", zero_division=0)),
            "samples": len(X),
            "features": X.shape[1],
        }

        # Register in database
        self._register_model(version, "random_forest", metrics, str(rf_path))
        self._register_model(version, "xgboost", metrics, str(xgb_path))

        logger.info("Models trained and saved: version=%s, samples=%d", version, len(X))
        return {
            "metrics": metrics,
            "model_paths": {"rf": str(rf_path), "xgb": str(xgb_path), "scaler": str(scaler_path)},
        }

    def _generate_version(self) -> str:
        """Generate timestamp-based version."""
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    def _update_latest_symlinks(self, version: str) -> None:
        """Update portable latest-model copies (works without Windows symlink privileges)."""
        targets = {
            "rf_model.pkl": f"rf_{version}.pkl",
            "xgb_model.json": f"xgb_{version}.json",
            "scaler.pkl": f"scaler_{version}.pkl",
            "river_model.pkl": f"river_{version}.pkl",
        }
        for alias, filename in targets.items():
            source = self.model_dir / filename
            if not source.is_file():
                if alias == "river_model.pkl":
                    (self.model_dir / alias).unlink(missing_ok=True)
                continue
            shutil.copy2(source, self.model_dir / alias)
        (self.model_dir / "latest_version.txt").write_text(version, encoding="utf-8")

    def _register_model(self, version: str, model_type: str, metrics: dict, file_path: str) -> None:
        """Register model in database."""
        import json as json_lib
        self.repo.save_model_registry({
            "version": f"{model_type}_{version}",
            "model_type": model_type,
            "metrics": json_lib.dumps(metrics),
            "file_path": file_path,
            "status": "VALIDATED",
            "is_active": False,
        })

    def _save_validation_record(self, version: str, validation: dict) -> None:
        """Save validation results for failed validation."""
        val_dir = self.model_dir / "validation"
        val_dir.mkdir(parents=True, exist_ok=True)
        import json as json_lib
        with open(val_dir / f"validation_{version}.json", "w") as f:
            json_lib.dump(validation, f, indent=2)

    def train_river_online(self, X: np.ndarray, y: np.ndarray, version: str | None = None) -> compose.Pipeline | None:
        """Train River online learning model for incremental updates."""
        try:
            model = compose.Pipeline(
                ("scaler", preprocessing.StandardScaler()),
                ("model", tree.HoeffdingTreeClassifier(
                    grace_period=100,
                    split_confidence=1e-5,
                    tie_threshold=0.05,
                ))
            )

            for xi, yi in zip(X, y):
                model.learn_one(dict(enumerate(xi)), yi)

            # Save River model
            version = version or self._generate_version()
            river_path = self.model_dir / f"river_{version}.pkl"
            joblib.dump(model, river_path)

            logger.info("River online model trained and saved: %s", river_path)
            return model
        except Exception as exc:
            logger.error("River training failed: %s", exc)
            return None

    def retrain_if_needed(self, predictor: Predictor) -> dict[str, Any]:
        """Check if retraining is needed and execute if so."""
        from sqlalchemy import select

        from config import MODEL_RETRAIN_MIN_DAYS, MODEL_RETRAIN_MIN_NEW_SAMPLES
        from database.models import ModelRegistryModel

        with self.repo._get_session() as session:
            stmt = (
                select(ModelRegistryModel)
                .where(ModelRegistryModel.is_active.is_(True))
                .order_by(ModelRegistryModel.trained_at.desc())
                .limit(1)
            )
            active = session.scalars(stmt).first()

        if not active:
            logger.info("No active model found; starting the initial training attempt")
            return self.train_and_validate()

        trained_at = active.trained_at
        if trained_at.tzinfo is None:
            trained_at = trained_at.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - trained_at).days
        predictions = self.repo.get_predictions_history(limit=10000)
        resolved_since_training = 0
        recent_resolved = []
        for prediction in predictions:
            if prediction.is_correct is None:
                continue
            created_at = prediction.created_at
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at and created_at > trained_at:
                resolved_since_training += 1
            recent_resolved.append(bool(prediction.is_correct))
            if len(recent_resolved) >= 100:
                break

        recent_accuracy = (
            sum(recent_resolved) / len(recent_resolved) if recent_resolved else None
        )
        should_retrain = (
            days_since >= MODEL_RETRAIN_MIN_DAYS
            or resolved_since_training >= MODEL_RETRAIN_MIN_NEW_SAMPLES
            or (len(recent_resolved) >= 50 and recent_accuracy is not None and recent_accuracy < 0.48)
        )
        if should_retrain:
            logger.info(
                "Retraining triggered: model_age_days=%d, new_resolved=%d, recent_accuracy=%s",
                days_since, resolved_since_training, recent_accuracy,
            )
            return self.train_and_validate()

        return {
            "status": "model_current",
            "days_since_train": days_since,
            "new_resolved_samples": resolved_since_training,
            "recent_accuracy": recent_accuracy,
        }


class LearningOrchestrator:
    """Orchestrates the complete learning loop: predict → wait → label → train → validate → promote."""

    def __init__(self, repo: Repository, predictor: Predictor, trainer: ModelTrainer | None = None):
        self.repo = repo
        self.predictor = predictor
        self.trainer = trainer or ModelTrainer(repo)

    async def run_learning_cycle(self) -> dict[str, Any]:
        """Execute one full learning cycle."""
        from learning.outcome_labeler import OutcomeLabeler

        results = {}

        # 1. Label outcomes for resolved predictions
        labeler = OutcomeLabeler(self.repo)
        labeled = labeler.evaluate_unresolved()
        results["outcomes_labeled"] = labeled

        # 2. Respect the operator's automatic-training and ML switches.
        from config import AUTO_MODEL_TRAINING, ML_ENABLED
        if AUTO_MODEL_TRAINING and ML_ENABLED:
            retrain_result = self.trainer.retrain_if_needed(self.predictor)
        else:
            retrain_result = {"status": "disabled"}
        results["retrain"] = retrain_result

        # 3. If new model trained and validated, promote it
        if retrain_result.get("status") == "trained":
            version = retrain_result.get("version")
            validation = retrain_result.get("validation", {})
            if validation.get("ensemble_passes", False):
                await self._promote_model(version)
                results["promoted"] = version

        return results

    async def _promote_model(self, version: str) -> None:
        """Promote newly validated model."""
        self.repo.promote_model(f"random_forest_{version}")
        self.repo.promote_model(f"xgboost_{version}")
        logger.info("Promoted model version %s", version)

        # Reload predictor
        self.predictor._load_latest()