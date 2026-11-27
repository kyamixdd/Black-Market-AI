"""Dataset builder: constructs feature/target datasets from historical predictions and outcomes."""
from __future__ import annotations

import logging
import json
from pathlib import Path

import numpy as np
from sqlalchemy import select

from config import SUPPORTED_TIMEFRAMES, WALK_FORWARD_MIN_SAMPLES
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

    def build_dataset(self, min_samples: int = WALK_FORWARD_MIN_SAMPLES, *, include_timestamps: bool = False, include_metadata: bool = False):
        """
        Build feature matrix X and target vector y from resolved predictions.
        Returns (X, y) where y is class indices: 0=DOWN, 1=FLAT, 2=UP
        """
        predictions = self.repo.get_predictions_history(limit=10000)

        # Chronology is explicit: repository order is not a training guarantee.
        resolved = sorted(
            (p for p in predictions if p.is_correct is not None and p.created_at is not None),
            key=lambda p: p.created_at,
        )
        logger.info("Found %d resolved predictions out of %d total", len(resolved), len(predictions))

        if len(resolved) < min_samples:
            logger.warning("Insufficient resolved samples: %d < %d required", len(resolved), min_samples)
            empty = (np.array([]), np.array([]))
            if include_metadata:
                return (*empty, np.array([], dtype=np.int64), {key: np.array([]) for key in ("timestamps", "actual_return_pct", "regimes", "horizon_minutes", "transaction_costs", "markets")})
            return (*empty, np.array([], dtype=np.int64)) if include_timestamps else empty

        X_list = []
        y_list = []
        timestamp_list = []
        return_list = []
        regime_list = []
        horizon_list = []
        cost_list = []
        market_list = []

        for pred in resolved:
            try:
                features = None
                if pred.feature_values:
                    try:
                        vector = np.asarray(json.loads(pred.feature_values), dtype=np.float32)
                        if vector.ndim == 1 and vector.size > 0 and np.isfinite(vector).all():
                            features = vector
                    except (TypeError, ValueError, json.JSONDecodeError):
                        logger.warning("Ignoring invalid saved features for %s", pred.prediction_id)
                if features is None:
                    features = self._build_features_for_prediction(pred)
                if features is not None:
                    X_list.append(features)
                    y_list.append(self._outcome_to_class(pred.actual_outcome))
                    timestamp_list.append(
                        int(pred.eval_time.timestamp() * 1000)
                        if pred.eval_time is not None
                        else int(pred.created_at.timestamp() * 1000)
                        + int(pred.horizon_minutes or 60) * 60 * 1000
                    )
                    return_list.append(float(pred.actual_return_pct) if pred.actual_return_pct is not None else np.nan)
                    regime_list.append(str(pred.regime or "UNKNOWN").upper())
                    horizon_list.append(int(pred.horizon_minutes or 60))
                    cost_list.append(float(pred.transaction_costs) if pred.transaction_costs is not None else np.nan)
                    market_list.append(str(pred.market or "UNKNOWN").upper())
            except Exception as exc:
                logger.warning("Failed to build features for %s: %s", pred.prediction_id, exc)
                continue

        if not X_list:
            empty = (np.array([]), np.array([]))
            return (*empty, np.array([], dtype=np.int64)) if include_timestamps else empty

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.int32)
        timestamps = np.asarray(timestamp_list, dtype=np.int64)
        order = np.argsort(timestamps, kind="stable")
        X, y, timestamps = X[order], y[order], timestamps[order]
        metadata = {
            # ``timestamps`` is already sorted with X/y above. Applying the
            # original permutation a second time detached economic time
            # periods from the OOF rows, corrupting compounded drawdown and
            # fold/regime return evidence.
            "timestamps": timestamps,
            "actual_return_pct": np.asarray(return_list, dtype=np.float64)[order],
            "regimes": np.asarray(regime_list, dtype=object)[order],
            "horizon_minutes": np.asarray(horizon_list, dtype=np.int32)[order],
            "transaction_costs": np.asarray(cost_list, dtype=np.float64)[order],
            "markets": np.asarray(market_list, dtype=object)[order],
        }
        logger.info("Built dataset: X=%s, y=%s", X.shape, y.shape)
        if include_metadata:
            if not include_timestamps:
                raise ValueError("include_metadata requires include_timestamps=True")
            return X, y, timestamps, metadata
        return (X, y, timestamps) if include_timestamps else (X, y)

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
        timeframes = SUPPORTED_TIMEFRAMES
        ohlc_data = {}

        with self.session_maker() as session:
            for tf in timeframes:
                stmt = (
                    select(CandleModel)
                    .where(
                        CandleModel.symbol == symbol,
                        CandleModel.market == market,
                        CandleModel.timeframe == tf,
                        CandleModel.close_time <= timestamp_ms,
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

    def save_dataset(self, X: np.ndarray, y: np.ndarray, version: str, timestamps: np.ndarray | None = None) -> str:
        """Save dataset to disk for reproducibility."""
        data_dir = Path(__file__).resolve().parents[1] / "data" / "datasets"
        data_dir.mkdir(parents=True, exist_ok=True)

        path = data_dir / f"dataset_{version}.npz"
        if timestamps is not None and (np.asarray(timestamps).ndim != 1 or len(timestamps) != len(y)):
            raise ValueError("timestamps must be a 1D array aligned with y")
        payload = {"X": X, "y": y}
        if timestamps is not None:
            payload["timestamps"] = np.asarray(timestamps, dtype=np.int64)
        np.savez_compressed(path, **payload)
        logger.info("Saved dataset to %s", path)
        return str(path)

    def load_dataset(self, version: str, *, include_timestamps: bool = False):
        """Load dataset from disk."""
        data_dir = Path(__file__).resolve().parents[1] / "data" / "datasets"
        path = data_dir / f"dataset_{version}.npz"
        data = np.load(path)
        if include_timestamps:
            if "timestamps" not in data:
                raise ValueError("saved dataset does not contain timestamps; rebuild it chronologically")
            return data["X"], data["y"], data["timestamps"]
        return data["X"], data["y"]
