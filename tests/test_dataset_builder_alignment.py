"""Dataset rows and economic metadata must share one chronological permutation."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import numpy as np

from learning.dataset_builder import DatasetBuilder


def test_metadata_timestamps_remain_aligned_after_chronological_sort():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            prediction_id=f"p{i}",
            is_correct=True,
            created_at=base + timedelta(hours=i),
            eval_time=base + timedelta(hours=hour),
            feature_values=json.dumps([float(i)]),
            actual_return_pct=float(i + 1),
            actual_outcome=outcome,
            regime=regime,
            horizon_minutes=60,
            transaction_costs=0.0008,
            market="SPOT",
        )
        for i, (hour, outcome, regime) in enumerate(
            [(2, "UP", "TRENDING"), (0, "DOWN", "RANGING"), (1, "FLAT", "HIGH_VOLATILITY")]
        )
    ]
    builder = object.__new__(DatasetBuilder)
    builder.repo = SimpleNamespace(get_predictions_history=lambda limit: rows)

    X, y, timestamps, metadata = builder.build_dataset(
        min_samples=1, include_timestamps=True, include_metadata=True
    )

    assert X[:, 0].tolist() == [1.0, 2.0, 0.0]
    assert y.tolist() == [0, 1, 2]
    assert timestamps.tolist() == metadata["timestamps"].tolist()
    assert metadata["actual_return_pct"].tolist() == [2.0, 3.0, 1.0]
    assert metadata["regimes"].tolist() == ["RANGING", "HIGH_VOLATILITY", "TRENDING"]

