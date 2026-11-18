"""Dataset builder: constructs feature/target datasets from historical predictions and outcomes."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from config import WALK_FORWARD_MIN_SAMPLES
from database.connection import get_session_maker
from database.models import CandleModel, PredictionModel
from database.repositories import Repository
from learning.feature_engine import FeatureEngine

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """Builds training datasets from historical predictions with known outcomes."""

    def __init__(self, repo: Repository, feature_engine: FeatureEngine | None = None):
        self.repo = repo
        self.feature_engine = feature_engine or FeatureEngine()
        self.session_maker = get_session_maker()

    def build_dataset(self, min_samples: int = WALK_FORWARD_MIN_SAMPLES) -> tuple[np.ndarray, np.ndarray]:
        """
        Build feature matrix X and target vector y from resolved predictions.
        Returns (X, y) where y is class indices: 0=DOWN, 1=FLAT, 2=UP
        """
        predictions = self.repo.get_predictions_history(limit=10000)

        # Filter to resolved predictions with outcomes
        resolved = [p for p in predictions if p.is_correct is not None]
        logger.info("Found %d resolved predictions out of %d total", len(resolved), len(predictions))

        if len(resolved) < min_samples:
            logger.warning("Insufficient resolved samples: %d < %d required", len(resolved), min_samples)
            return np.array([]), np.array([])

        X_list = []
        y_list = []

        for pred in resolved:
            try:
                features = self._build_features_for_prediction(pred)
                if features is not None:
                    X_list.append(features)
                    y_list.append(self._outcome_to_class(pred.actual_outcome))
            except Exception as exc:
                logger.warning("Failed to build features for %s: %s", pred.prediction_id, exc)
                continue

        if not X_list:
            return np.array([]), np.array([])

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.int32)
        logger.info("Built dataset: X=%s, y=%s", X.shape, y.shape)
        return X, y

    def _build_features_for_prediction(self, pred: PredictionModel) -> np.ndarray | None:
        """Build feature vector for a prediction at its creation time."""
        # Get OHLC data around prediction time
        created_ms = int(pred.created_at.timestamp() * 1000)
        ohlc_data = self._get_ohlc_data(pred.symbol, pred.market, created_ms)

        if not ohlc_data:
            return None

        return self.feature_engine.build_features(pred.symbol, pred.market, ohlc_data)

    def _get_ohlc_data(self, symbol: str, market: str, timestamp_ms: int,
                       lookback_candles: int = 200) -> dict[str, dict[str, np.ndarray]] | None:
        """Get multi-timeframe OHLC data up to the given timestamp."""
        timeframes = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
        ohlc_data = {}

        with self.session_maker() as session:
            for tf in timeframes:
                stmt = (
                    select(CandleModel)
                    .where(
                        CandleModel.symbol == symbol,
                        CandleModel.market == market,
                        CandleModel.timeframe == tf,
                        CandleModel.open_time <= timestamp_ms,
                    )
                    .order_by(CandleModel.open_time.desc())
                    .limit(lookback_candles)
                )
                candles = list(session.scalars(stmt).all())
                if len(candles) >= 20:  # Minimum for indicators
                    candles.reverse()
                    ohlc_data[tf] = {
                        "open": np.array([c.open for c in candles], dtype=np.float32),
                        "high": np.array([c.high for c in candles], dtype=np.float32),
                        "low": np.array([c.low for c in candles], dtype=np.float32),
                        "close": np.array([c.close for c in candles], dtype=np.float32),
                        "volume": np.array([c.volume for c in candles], dtype=np.float32),
                    }

        return ohlc_data if ohlc_data else None

    def _outcome_to_class(self, outcome: str) -> int:
        """Convert outcome string to class index."""
        return {"DOWN": 0, "FLAT": 1, "UP": 2}.get(outcome, 1)

    def save_dataset(self, X: np.ndarray, y: np.ndarray, version: str) -> str:
        """Save dataset to disk for reproducibility."""
        data_dir = Path(__file__).resolve().parents[1] / "data" / "datasets"
        data_dir.mkdir(parents=True, exist_ok=True)

        path = data_dir / f"dataset_{version}.npz"
        np.savez_compressed(path, X=X, y=y)
        logger.info("Saved dataset to %s", path)
        return str(path)

    def load_dataset(self, version: str) -> tuple[np.ndarray, np.ndarray]:
        """Load dataset from disk."""
        data_dir = Path(__file__).resolve().parents[1] / "data" / "datasets"
        path = data_dir / f"dataset_{version}.npz"
        data = np.load(path)
        return data["X"], data["y"]