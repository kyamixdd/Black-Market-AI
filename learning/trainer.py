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
from learning.confidence_gate import ModelPromotionGate

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Trains and validates ML models for the hybrid learning engine."""

    def __init__(self, repo: Repository, dataset_builder: DatasetBuilder | None = None):
        self.repo = repo
        self.dataset_builder = dataset_builder or DatasetBuilder(repo)
        self.validator = WalkForwardValidator()
        self.model_dir = Path(MODELS_DIR)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.last_river_path: Path | None = None

    def train_and_validate(self, X: np.ndarray | None = None, y: np.ndarray | None = None, timestamps: np.ndarray | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Full training pipeline: build dataset, validate, train, register."""
        # 1. Build dataset
        if X is None or y is None:
            X, y, timestamps, metadata = self.dataset_builder.build_dataset(include_timestamps=True, include_metadata=True)
        if len(X) == 0:
            return {"status": "insufficient_data", "samples": 0}

        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int32)
        if X.ndim != 2 or y.ndim != 1 or len(X) != len(y) or len(np.unique(y)) < 2:
            return {"status": "insufficient_data", "samples": len(y), "reason": "invalid_or_single_class_dataset"}

        # Require timestamps for leakage-safe chronological validation.
        if timestamps is None:
            return {"status": "validation_failed", "samples": len(y), "reason": "timestamps_required_for_walk_forward"}
        timestamps = np.asarray(timestamps)
        if timestamps.ndim != 1 or len(timestamps) != len(y):
            return {"status": "validation_failed", "samples": len(y), "reason": "timestamp_alignment_error"}

        if metadata is None:
            return {"status": "validation_failed", "samples": len(y), "reason": "cost_and_regime_metadata_required_for_promotion"}
        required_metadata = ("timestamps", "actual_return_pct", "transaction_costs", "regimes", "markets", "horizon_minutes")
        if any(key not in metadata or len(np.asarray(metadata[key]).reshape(-1)) != len(y) for key in required_metadata):
            return {"status": "validation_failed", "samples": len(y), "reason": "promotion_metadata_alignment_error"}

        # 2. Walk-forward validation; live forecasts use a one-hour target horizon.
        validation = self.validator.validate_ensemble(X, y, timestamps=timestamps, purge_gap_ms=60 * 60 * 1000)
        champion_validation = self._validate_active_champions(X, y, timestamps)
        promotion_gate = ModelPromotionGate().evaluate(
            validation, sample_count=len(y), economic_metadata=metadata,
            champion_validation=champion_validation,
        )
        promotion_gate["validation_provenance"] = {
            "method": "purged_timestamp_walk_forward",
            "out_of_sample": True,
            "timestamps_required": True,
            "purge_gap_ms": 60 * 60 * 1000,
            "target_horizon_ms": 60 * 60 * 1000,
            "sample_count": int(len(y)),
            "rf_oof_count": int(len(validation.get("rf", {}).get("out_of_fold") or [])),
            "xgb_oof_count": int(len(validation.get("xgb", {}).get("out_of_fold") or [])),
        }
        validation["promotion_gate"] = promotion_gate
        logger.info("Validation complete: RF passes=%s, XGB passes=%s",
                    validation["rf"].get("passes_threshold", False),
                    validation["xgb"].get("passes_threshold", False))

        # 3. If validation passes, train final models on full dataset
        if promotion_gate["passes"]:
            version = self._generate_version()
            train_result = self._train_final_models(X, y, version, promotion_gate)
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

    def _validate_active_champions(self, X: np.ndarray, y: np.ndarray, timestamps: np.ndarray) -> dict[str, Any]:
        """Evaluate active RF/XGB champions on identical chronological folds."""
        try:
            registry = self.repo.get_model_registry()
        except Exception:
            logger.exception("Unable to load active champion registry")
            return {}
        results: dict[str, Any] = {}
        for model_type, gate_name in (("random_forest", "rf"), ("xgboost", "xgb")):
            active = [
                item for item in registry
                if getattr(item, "model_type", None) == model_type
                and bool(getattr(item, "is_active", False))
                and (bool(getattr(item, "is_champion", False)) or str(getattr(item, "status", "")).upper() in {"PROMOTED", "CHAMPION"})
            ]
            if not active:
                logger.warning("Promotion blocked: no active champion for %s", model_type)
                # The first validated model has no incumbent to compare
                # against. Absolute walk-forward/economic/calibration gates
                # still apply before its first activation.
                results[gate_name] = {"status": "not_applicable_no_active_champion"}
                continue
            champion = max(active, key=lambda item: getattr(item, "trained_at", datetime.min.replace(tzinfo=timezone.utc)))
            file_path = getattr(champion, "file_path", None)
            if not file_path or not Path(file_path).is_file():
                logger.warning("Promotion blocked: champion model file unavailable for %s", model_type)
                continue
            def champion_factory(path=file_path, kind=model_type):
                if kind == "xgboost":
                    model = xgb.XGBClassifier()
                    model.load_model(str(path))
                    return model
                return joblib.load(path)
            try:
                results[gate_name] = self.validator.validate(
                    X, y, champion_factory, metric="f1", timestamps=timestamps,
                    purge_gap_ms=60 * 60 * 1000,
                )
            except Exception:
                logger.exception("Champion comparison validation failed for %s", model_type)
        return results

    def _train_final_models(self, X: np.ndarray, y: np.ndarray, version: str, promotion_gate: dict[str, Any]) -> dict[str, Any]:
        """Fit final deployable models only after strict OOF gate approval.

        Full-data fit metrics are diagnostics only; promotion evidence is the
        separately persisted purged walk-forward gate result.
        """
        if not self._promotion_evidence_passes(promotion_gate):
            raise ValueError("cannot fit/register a deployable model without complete out-of-sample promotion evidence")
        # Train RF
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)
        rf = RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42, n_jobs=-1)
        rf.fit(Xs, y)

        # Train XGBoost
        xgb_model = xgb.XGBClassifier(
            n_estimators=150, max_depth=6, learning_rate=0.05,
            random_state=42, n_jobs=1, eval_metric="mlogloss"
        )
        xgb_model.fit(Xs, y)

        # Save models
        rf_path = self.model_dir / f"rf_{version}.pkl"
        xgb_path = self.model_dir / f"xgb_{version}.json"
        scaler_path = self.model_dir / f"scaler_{version}.pkl"

        joblib.dump(rf, rf_path)
        xgb_model.save_model(str(xgb_path))
        joblib.dump(scaler, scaler_path)

        # Update symlinks to latest
        self._update_latest_symlinks(version)

        # Calculate training metrics
        rf_pred = rf.predict(Xs)
        xgb_pred = xgb_model.predict(Xs)
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
        """Atomically copy latest model files (Windows does not guarantee symlink rights)."""
        latest_files = {
            "rf_model.pkl": f"rf_{version}.pkl",
            "xgb_model.json": f"xgb_{version}.json",
            "scaler.pkl": f"scaler_{version}.pkl",
        }
        for name, source_name in latest_files.items():
            target = self.model_dir / name
            source = self.model_dir / source_name
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(source, temporary)
            temporary.replace(target)

    @staticmethod
    def _promotion_evidence_passes(evidence: dict[str, Any] | None) -> bool:
        if not isinstance(evidence, dict) or evidence.get("passes") is not True:
            return False
        provenance = evidence.get("validation_provenance") or {}
        def safe_int(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError, OverflowError):
                return -1
        return (
            provenance.get("method") == "purged_timestamp_walk_forward"
            and provenance.get("out_of_sample") is True
            and provenance.get("timestamps_required") is True
            and safe_int(provenance.get("purge_gap_ms", 0)) >= safe_int(provenance.get("target_horizon_ms", 1))
            and safe_int(provenance.get("target_horizon_ms", 0)) > 0
            and safe_int(provenance.get("rf_oof_count", 0)) > 0
            and safe_int(provenance.get("xgb_oof_count", 0)) > 0
            and (evidence.get("models") or {}).get("rf", {}).get("passes") is True
            and (evidence.get("models") or {}).get("xgb", {}).get("passes") is True
            and (evidence.get("economic_evidence") or {}).get("rf", {}).get("status") == "ok"
            and (evidence.get("economic_evidence") or {}).get("xgb", {}).get("status") == "ok"
            and (evidence.get("champion_evidence") or {}).get("rf", {}).get("status") in {"ok", "not_applicable_no_active_champion"}
            and (evidence.get("champion_evidence") or {}).get("xgb", {}).get("status") in {"ok", "not_applicable_no_active_champion"}
        )

    def _register_model(self, version: str, model_type: str, metrics: dict, file_path: str, promotion_gate: dict[str, Any]) -> None:
        """Register candidate with persisted out-of-sample evidence; never activate here."""
        import json as json_lib
        if not self._promotion_evidence_passes(promotion_gate):
            raise ValueError("refusing to register model without complete promotion evidence")
        self.repo.save_model_registry({
            "version": f"{model_type}_{version}",
            "model_type": model_type,
            "metrics": json_lib.dumps(metrics),
            "file_path": file_path,
            "status": "CANDIDATE",
            "is_active": False,
            "is_champion": False,
            "evaluation_data": json_lib.dumps({
                "promotion_gate": promotion_gate,
                "training_metrics_in_sample_only": metrics,
            }),
        })

    def _save_validation_record(self, version: str, validation: dict) -> None:
        """Save validation results for failed validation."""
        val_dir = self.model_dir / "validation"
        val_dir.mkdir(parents=True, exist_ok=True)
        import json as json_lib
        with open(val_dir / f"validation_{version}.json", "w") as f:
            json_lib.dump(validation, f, indent=2, default=lambda value: value.item() if isinstance(value, np.generic) else str(value))

    def train_river_online(self, X: np.ndarray, y: np.ndarray) -> compose.Pipeline | None:
        """Train River online learning model for incremental updates."""
        try:
            model = compose.Pipeline(
                ("scaler", preprocessing.StandardScaler()),
                ("model", tree.HoeffdingTreeClassifier(
                    grace_period=100,
                    delta=1e-5,
                    tau=0.05,
                ))
            )

            for xi, yi in zip(X, y):
                model.learn_one(dict(enumerate(xi)), yi)

            # Save River model
            version = self._generate_version()
            river_path = self.model_dir / f"river_{version}.pkl"
            joblib.dump(model, river_path)
            self.last_river_path = river_path
            self.repo.save_model_registry({
                "version": f"river_{version}",
                "model_type": "river",
                "metrics": {"samples": int(len(X)), "features": int(X.shape[1])},
                "file_path": str(river_path),
                "status": "TRAINED",
                "is_active": False,
            })

            logger.info("River online model trained and saved: %s", river_path)
            return model
        except Exception as exc:
            logger.error("River training failed: %s", exc)
            return None

    def retrain_if_needed(self, predictor: Predictor) -> dict[str, Any]:
        """Check if retraining is needed and execute if so."""
        from sqlalchemy import select

        from config import MODEL_RETRAIN_MIN_DAYS
        from database.connection import get_session_maker
        from database.models import ModelRegistryModel

        session_maker = get_session_maker()
        with session_maker() as session:
            stmt = (
                select(ModelRegistryModel)
                .where(ModelRegistryModel.is_active.is_(True))
                .order_by(ModelRegistryModel.trained_at.desc())
                .limit(1)
            )
            active = session.scalars(stmt).first()

        if not active:
            return self.train_and_validate()

        days_since = (datetime.now(timezone.utc) - active.trained_at).days
        if days_since >= MODEL_RETRAIN_MIN_DAYS:
            logger.info("Model age %d days >= %d, retraining...", days_since, MODEL_RETRAIN_MIN_DAYS)
            return self.train_and_validate()

        return {"status": "model_current", "days_since_train": days_since}


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

        # 2. Check if retraining is needed
        retrain_result = self.trainer.retrain_if_needed(self.predictor)
        results["retrain"] = retrain_result

        # 3. If new model trained and validated, promote it
        if retrain_result.get("status") == "trained":
            version = retrain_result.get("version")
            validation = retrain_result.get("validation", {})
            if version and validation.get("promotion_gate", {}).get("passes", False):
                if await self._promote_model(version, validation):
                    results["promoted"] = version
                else:
                    results["promotion_blocked"] = version
            else:
                results["promotion_blocked"] = version

        return results

    async def _promote_model(self, version: str, validation: dict[str, Any] | None = None) -> bool:
        """Activate only the exact candidate version carrying complete OOF gate evidence."""
        gate = (validation or {}).get("promotion_gate") or {}
        if not ModelTrainer._promotion_evidence_passes(gate):
            logger.error("Promotion blocked for %s: complete out-of-sample gate evidence missing", version)
            return False
        versions = [f"random_forest_{version}", f"xgboost_{version}"]
        promoted = self.repo.promote_models(versions)
        if not promoted:
            logger.error("Repository rejected promotion for %s; candidate remains inactive", version)
            return False
        # Update runtime aliases only after the atomic database promotion succeeds.
        self.trainer._update_latest_symlinks(version)
        logger.info("Promoted validated model version %s", version)
        self.predictor._load_latest()
        return True
