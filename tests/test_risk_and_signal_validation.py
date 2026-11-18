import math

import numpy as np

from intelligence.signal_validator import SignalValidator
from paper_trading.risk_manager import RiskManager


def make_risk_manager():
    return RiskManager(
        max_risk_pct=1.0,
        max_daily_loss_pct=5.0,
        max_open_risk_pct=10.0,
        max_leverage=5.0,
        max_spot_positions=5,
        max_futures_positions=5,
    )


def test_daily_profit_does_not_trigger_loss_limit():
    assert make_risk_manager().check_daily_loss(250.0, 1000.0)


def test_daily_loss_below_limit_is_allowed():
    assert make_risk_manager().check_daily_loss(-49.0, 1000.0)


def test_daily_loss_at_limit_is_blocked():
    assert not make_risk_manager().check_daily_loss(-50.0, 1000.0)


def test_non_positive_balance_is_blocked():
    assert not make_risk_manager().check_daily_loss(-1.0, 0.0)


def valid_long_signal():
    return {
        "signal_id": "test-1",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "strategy": "test",
        "direction": "LONG",
        "timeframe": "5m",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": [105.0],
    }


def test_valid_long_signal_passes():
    assert SignalValidator().validate(valid_long_signal()) == (True, "OK")


def test_unknown_direction_is_rejected():
    signal = valid_long_signal()
    signal["direction"] = "SIDEWAYS"
    assert SignalValidator().validate(signal)[0] is False


def test_non_finite_prices_are_rejected():
    signal = valid_long_signal()
    signal["entry"] = math.nan
    assert SignalValidator().validate(signal)[0] is False


def test_invalid_take_profit_type_is_rejected():
    signal = valid_long_signal()
    signal["take_profit"] = [float("inf")]
    assert SignalValidator().validate(signal)[0] is False


def test_invalid_numeric_feature_vector_is_rejected_by_predictor():
    from learning.predictor import Predictor

    predictor = Predictor()
    predictor.is_trained = True

    class DummyModel:
        n_features_in_ = 2
        classes_ = np.array([0, 1, 2])

        def predict_proba(self, features):
            return np.array([[0.2, 0.3, 0.5]])

    predictor.rf_model = DummyModel()
    predictor.xgb_model = DummyModel()
    try:
        predictor.predict(np.array([1.0, np.nan]))
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("Expected non-finite features to be rejected")


@pytest.mark.asyncio
async def test_decision_engine_publishes_rejection_with_event_envelope_fields():
    from core.event_bus import EventBus
    from core.event_models import EventType
    from intelligence.decision_engine import DecisionEngine

    bus = EventBus()
    rejected = []

    async def capture(event):
        rejected.append(event)

    bus.subscribe(EventType.SIGNAL_REJECTED, capture)
    consumer = asyncio.create_task(bus.run())
    engine = DecisionEngine(bus)
    await engine.evaluate_signal({
        "signal_id": "SIG-INVALID-SPOT-SHORT",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "strategy": "test",
        "direction": "SELL",
        "timeframe": "15m",
        "entry": 100.0,
        "stop_loss": 110.0,
        "take_profit": [90.0],
        "reasons": ["test"],
    })
    await bus.stop()
    await consumer

    assert len(rejected) == 1
    assert rejected[0].symbol == "BTCUSDT"
    assert rejected[0].market == "SPOT"
    assert "does not support short" in rejected[0].payload["reject_reason"]
