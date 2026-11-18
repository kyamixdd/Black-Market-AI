"""ML Predictor: local models for outcome prediction."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from config import ML_ENABLED

logger = logging.getLogger(__name__)
CLASS_NAMES = {0: "DOWN", 1: "FLAT", 2: "UP"}


class Predictor:
    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir or Path(__file__).resolve().parents[1] / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.rf_model: RandomForestClassifier | None = None
        self.xgb_model: xgb.XGBClassifier | None = None
        self.river_model: Any | None = None
        # Retained for compatibility with older model bundles. Current RF/XGB
        # training and validation use raw features, so inference must too.
        self.scaler = StandardScaler()
        self.is_trained = False
        self.version = "0001"
        if ML_ENABLED:
            self._load_latest()

    def _load_latest(self) -> None:
        rf_path = self.model_dir / "rf_model.pkl"
        xgb_path = self.model_dir / "xgb_model.json"
        scaler_path = self.model_dir / "scaler.pkl"
        river_path = self.model_dir / "river_model.pkl"
        if rf_path.exists() and xgb_path.exists():
            try:
                self.rf_model = joblib.load(rf_path)
                self.xgb_model = xgb.XGBClassifier()
                self.xgb_model.load_model(str(xgb_path))
                if river_path.exists():
                    try:
                        self.river_model = joblib.load(river_path)
                    except Exception as river_exc:
                        self.river_model = None
                        logger.warning("Failed to load River model: %s", river_exc)
                version_file = self.model_dir / "latest_version.txt"
                if version_file.exists():
                    self.version = version_file.read_text(encoding="utf-8").strip() or self.version
                self.is_trained = True
                logger.info("Loaded batch models%s", " and River online model" if self.river_model else "")
            except Exception as exc:
                self.is_trained = False
                logger.warning("Failed to load models: %s", exc)

    @staticmethod
    def _class_probabilities(model: Any, features: np.ndarray) -> np.ndarray:
        """Return probabilities in the stable DOWN/FLAT/UP class order."""
        raw = model.predict_proba(features)[0]
        classes = getattr(model, "classes_", np.arange(len(raw)))
        aligned = np.zeros(3, dtype=np.float64)
        for class_value, probability in zip(classes, raw):
            try:
                class_index = int(class_value)
            except (TypeError, ValueError, OverflowError):
                continue
            if class_index in CLASS_NAMES:
                aligned[class_index] = float(probability)
        return aligned

    def predict(self, features: np.ndarray) -> dict[str, Any]:
        if not self.is_trained or self.rf_model is None or self.xgb_model is None:
            return {
                "prob_up": 0.33, "prob_down": 0.34, "prob_flat": 0.33,
                "predicted_class": "FLAT", "confidence": 0.0,
                "model_version": self.version,
            }

        X = np.asarray(features, dtype=np.float64).reshape(1, -1)
        if X.shape[1] == 0 or not np.isfinite(X).all():
            raise ValueError("Prediction features must be a non-empty finite vector")
        expected_features = getattr(self.rf_model, "n_features_in_", X.shape[1])
        if X.shape[1] != expected_features:
            raise ValueError(
                f"Expected {expected_features} features, received {X.shape[1]}"
            )

        # The trainer and walk-forward validator fit on raw feature values.
        # Applying StandardScaler only at inference creates train/serve skew.
        rf_probs = self._class_probabilities(self.rf_model, X)
        xgb_probs = self._class_probabilities(self.xgb_model, X)
        probability_sets = [rf_probs, xgb_probs]
        if self.river_model is not None:
            try:
                river_raw = self.river_model.predict_proba_one(dict(enumerate(X[0])))
                river_probs = np.zeros(3, dtype=np.float64)
                for class_value, probability in river_raw.items():
                    try:
                        class_index = int(class_value)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if class_index in CLASS_NAMES:
                        river_probs[class_index] = float(probability)
                if np.isfinite(river_probs).all() and river_probs.sum() > 0:
                    river_probs /= river_probs.sum()
                    probability_sets.append(river_probs)
            except Exception as exc:
                logger.warning("River inference failed; using batch ensemble only: %s", exc)
        probs = np.mean(probability_sets, axis=0)
        total = float(probs.sum())
        if not np.isfinite(probs).all() or total <= 0:
            raise ValueError("Models returned invalid class probabilities")
        probs /= total
        class_idx = int(np.argmax(probs))
        return {
            "prob_up": float(probs[2]),
            "prob_down": float(probs[0]),
            "prob_flat": float(probs[1]),
            "predicted_class": CLASS_NAMES[class_idx],
            "confidence": float(probs[class_idx]),
            "model_version": self.version,
        }

    def save(self, version: str) -> None:
        if self.rf_model is None or self.xgb_model is None:
            return
        artifacts = {
            "rf_model.pkl": f"rf_{version}.pkl",
            "xgb_model.json": f"xgb_{version}.json",
            "scaler.pkl": f"scaler_{version}.pkl",
        }
        joblib.dump(self.rf_model, self.model_dir / artifacts["rf_model.pkl"])
        self.xgb_model.save_model(str(self.model_dir / artifacts["xgb_model.json"]))
        joblib.dump(self.scaler, self.model_dir / artifacts["scaler.pkl"])
        if self.river_model is not None:
            river_name = f"river_{version}.pkl"
            joblib.dump(self.river_model, self.model_dir / river_name)
            artifacts["river_model.pkl"] = river_name
        for alias, filename in artifacts.items():
            shutil.copy2(self.model_dir / filename, self.model_dir / alias)
        (self.model_dir / "latest_version.txt").write_text(version, encoding="utf-8")
        self.version = version
