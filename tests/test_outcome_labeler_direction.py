"""Regression tests for independent, timestamp-safe prediction outcome labels."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from database.connection import Database
from database.models import CandleModel
from learning.outcome_labeler import OutcomeLabeler


@pytest.mark.parametrize(
    ("predicted", "entry", "exit", "expected", "correct", "expected_pnl"),
    [
        ("UP", 100.0, 101.0, "UP", True, 0.01),
        ("UP", 100.0, 99.0, "DOWN", False, -0.01),
        ("DOWN", 100.0, 99.0, "DOWN", True, 0.01),
        ("DOWN", 100.0, 101.0, "UP", False, -0.01),
    ],
)
def test_actual_outcome_is_independent_of_prediction(
    predicted, entry, exit, expected, correct, expected_pnl
):
    labeler = OutcomeLabeler(repo=None)
    created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    created_ms = int(created_at.timestamp() * 1000)
    horizon_ms = 60 * 60 * 1000
    requested_timestamps = []

    def price_at_time(_symbol, _market, timestamp_ms, _timeframe):
        requested_timestamps.append(timestamp_ms)
        return entry if timestamp_ms == created_ms else exit

    labeler._get_price_at_time = price_at_time
    labeler._calculate_costs = lambda *_args: 0.0
    prediction = SimpleNamespace(
        created_at=created_at,
        horizon_minutes=60,
        timeframe="1h",
        symbol="BTCUSDT",
        market="SPOT",
        predicted_class=predicted,
    )

    result = labeler._evaluate_prediction(prediction)

    assert result is not None
    assert result["actual_outcome"] == expected
    assert result["is_correct"] is correct
    assert result["actual_return_pct"] == pytest.approx((exit - entry) / entry)
    assert result["simulated_pnl"] == pytest.approx(expected_pnl)
    assert requested_timestamps == [created_ms, created_ms + horizon_ms]


def test_price_lookup_uses_only_candles_closed_at_target(monkeypatch, tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'closed_candles.db'}")
    db.init_db()
    session_maker = db.session_maker()
    target_ms = 1_700_000_000_000

    with session_maker() as session:
        session.add_all(
            [
                CandleModel(
                    symbol="BTCUSDT", market="SPOT", timeframe="1m",
                    open_time=target_ms - 60_000, close_time=target_ms,
                    open=99, high=101, low=98, close=100, volume=1,
                ),
                CandleModel(
                    symbol="BTCUSDT", market="SPOT", timeframe="1m",
                    open_time=target_ms, close_time=target_ms + 59_999,
                    open=100, high=110, low=99, close=109, volume=1,
                ),
            ]
        )
        session.commit()

    # _get_price_at_time imports the session factory inside the method.
    import database.connection as connection_module
    monkeypatch.setattr(connection_module, "get_session_maker", lambda: session_maker)

    labeler = OutcomeLabeler(repo=None)
    assert labeler._get_price_at_time(
        "BTCUSDT", "SPOT", target_ms, "1m"
    ) == pytest.approx(100.0)
    db.close()
