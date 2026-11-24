"""ML Predictor: local models for outcome prediction."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from config import ML_ENABLED, MODELS_DIR

logger = logging.getLogger(__name__)


class Predictor:
    def __init__(self, model_dir: Path | None = None):
        self.model_dir = Path(model_dir or MODELS_DIR)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.rf_model: RandomForestClassifier | None = None
        self.xgb_model: xgb.XGBClassifier | None = None
        self.scaler = StandardScaler()
        self.river_model: Any | None = None
        self.is_trained = False
        self.version = "0001"
        if ML_ENABLED:
            self._load_latest()

    def _load_latest(self) -> None:
        rf_path = self.model_dir / "rf_model.pkl"
        xgb_path = self.model_dir / "xgb_model.json"
        scaler_path = self.model_dir / "scaler.pkl"
        if rf_path.exists() and xgb_path.exists() and scaler_path.exists():
            try:
                self.rf_model = joblib.load(rf_path)
                self.xgb_model = xgb.XGBClassifier()
                self.xgb_model.load_model(xgb_path)
                self.scaler = joblib.load(scaler_path)
                self.is_trained = True
                latest = sorted(
                    (path for path in self.model_dir.glob("rf_*.pkl") if path.stem != "rf_model"),
                    key=lambda p: p.stat().st_mtime,
                )
                if latest:
                    self.version = re.sub(r"^rf_|\.pkl$", "", latest[-1].name)
                logger.info("Loaded existing models")
            except Exception as exc:
                logger.warning("Failed to load models: %s", exc)

        # River candidates are not loaded from disk automatically. Only a model
        # promoted through the repository's complete out-of-sample gate may
        # become part of the active prediction ensemble.

    def predict(self, features: np.ndarray) -> dict[str, Any]:
        if not self.is_trained:
            return {
                "prob_up": 0.33, "prob_down": 0.34, "prob_flat": 0.33,
                "predicted_class": "FLAT", "confidence": 0.0,
                "model_version": self.version,
            }
        sources: list[dict[int, float]] = []
        X = features.reshape(1, -1)
        if self.rf_model is not None and self.xgb_model is not None:
            Xs = self.scaler.transform(X)
            for model in (self.rf_model, self.xgb_model):
                values = model.predict_proba(Xs)[0]
                sources.append({int(label): float(value) for label, value in zip(model.classes_, values)})
        if self.river_model is not None:
            river_probs = self.river_model.predict_proba_one(dict(enumerate(features.tolist())))
            if river_probs:
                sources.append({int(label): float(value) for label, value in river_probs.items()})
        if not sources:
            return {
                "prob_up": 0.33, "prob_down": 0.34, "prob_flat": 0.33,
                "predicted_class": "FLAT", "confidence": 0.0,
                "model_version": self.version,
            }
        labels = {0, 1, 2}
        probs_by_class = {
            label: sum(source.get(label, 0.0) for source in sources) / len(sources)
            for label in labels
        }
        total = sum(probs_by_class.values())
        if total > 0:
            probs_by_class = {label: value / total for label, value in probs_by_class.items()}
        class_idx = max(probs_by_class, key=probs_by_class.get)
        classes = {0: "DOWN", 1: "FLAT", 2: "UP"}
        return {
            "prob_up": float(probs_by_class[2]),
            "prob_down": float(probs_by_class[0]),
            "prob_flat": float(probs_by_class[1]),
            "predicted_class": classes[class_idx],
            "confidence": float(probs_by_class[class_idx]),
            "model_version": self.version,
        }

    def save(self, version: str) -> None:
        if self.rf_model is None or self.xgb_model is None:
            return
        joblib.dump(self.rf_model, self.model_dir / f"rf_{version}.pkl")
        self.xgb_model.save_model(str(self.model_dir / f"xgb_{version}.json"))
        joblib.dump(self.scaler, self.model_dir / f"scaler_{version}.pkl")
        latest_files = {
            "rf_model.pkl": f"rf_{version}.pkl",
            "xgb_model.json": f"xgb_{version}.json",
            "scaler.pkl": f"scaler_{version}.pkl",
        }
        for name, source_name in latest_files.items():
            target = self.model_dir / name
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(self.model_dir / source_name, temporary)
            temporary.replace(target)
