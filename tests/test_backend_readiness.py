"""Regression tests for backend readiness fixes."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

from intelligence.feature_engine import FeatureEngine
from learning.dataset_builder import DatasetBuilder


def _ohlc(length=80):
    close = np.linspace(100.0, 120.0, length, dtype=np.float32)
    return {
        "open": close.copy(),
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close.copy(),
        "volume": np.linspace(1000.0, 2000.0, length, dtype=np.float32),
    }


def test_intelligence_feature_vector_has_fixed_width_for_any_timeframe_subset():
    engine = FeatureEngine()
    full = {tf: _ohlc() for tf in ("15m", "1h", "4h", "1d")}
    partial = {"15m": _ohlc()}

    full_features = engine.build_features("BTCUSDT", "SPOT", full)
    partial_features = engine.build_features("BTCUSDT", "SPOT", partial)
    empty_features = engine.build_features("BTCUSDT", "SPOT", {})

    assert full_features.shape == (48,)
    assert partial_features.shape == (48,)
    assert empty_features.shape == (48,)
    assert np.isfinite(full_features).all()
    assert np.isfinite(partial_features).all()
    assert np.isfinite(empty_features).all()


def test_dataset_builder_uses_stored_features_in_oldest_first_order():
    class FakeRepo:
        _session_maker = None

        def __init__(self, predictions):
            self.predictions = predictions

        def get_predictions_history(self, limit=500):
            return list(reversed(self.predictions))

    now = datetime.now(timezone.utc)
    predictions = []
    for index, outcome in enumerate(("UP", "DOWN", "FLAT")):
        predictions.append(SimpleNamespace(
            prediction_id=f"PRED-{index}",
            created_at=now + timedelta(minutes=index),
            is_correct=(index != 1),
            actual_outcome=outcome,
            feature_values=json.dumps([float(index), float(index + 10)]),
            symbol="BTCUSDT",
            market="SPOT",
        ))

    builder = DatasetBuilder(FakeRepo(predictions))
    X, y = builder.build_dataset(min_samples=3)

    assert X.tolist() == [[0.0, 10.0], [1.0, 11.0], [2.0, 12.0]]
    assert y.tolist() == [2, 0, 1]
