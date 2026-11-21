"""Tests for the learning performance dashboard API metrics."""
import pytest

from src_tauri.backend.api.routes import learning


class FakeSimulator:
    initial_spot_balance = 1000.0
    initial_futures_balance = 1000.0


class FakeBridge:
    simulator = FakeSimulator()

    def __init__(self, predictions=None, trades=None):
        self.predictions = predictions or []
        self.trades = trades or []

    def get_recent_predictions(self, limit=10000):
        return self.predictions[:limit]

    def get_recent_trades(self, limit=10000):
        return self.trades[:limit]


@pytest.mark.asyncio
async def test_performance_metrics_use_resolved_predictions_and_closed_trades(monkeypatch):
    predictions = [
        {"is_correct": True, "predicted_class": "UP", "actual_outcome": "UP"},
        {"is_correct": False, "predicted_class": "UP", "actual_outcome": "DOWN"},
        {"is_correct": True, "predicted_class": "DOWN", "actual_outcome": "DOWN"},
        {"is_correct": None, "predicted_class": "UP", "actual_outcome": None},
    ]
    trades = [
        {"closed_at": "2026-10-01T12:00:00+00:00", "pnl": 100.0},
        {"closed_at": "2026-10-02T12:00:00+00:00", "pnl": -50.0},
        {"closed_at": "2026-10-03T12:00:00+00:00", "pnl": 25.0},
        {"closed_at": None, "pnl": 1000.0},
    ]
    bridge = FakeBridge(predictions, trades)
    monkeypatch.setattr(learning, "get_bridge", lambda: bridge)

    result = await learning.get_model_performance()

    assert result["prediction_count"] == 3
    assert result["accuracy_pct"] == pytest.approx(200 / 3)
    assert result["precision_macro_pct"] == pytest.approx(75.0)
    assert result["recall_macro_pct"] == pytest.approx(75.0)
    assert result["trade_count"] == 3
    assert result["profit_factor"] == pytest.approx(2.5)
    assert result["win_rate_pct"] == pytest.approx(200 / 3)
    assert result["max_drawdown_pct"] > 0
    assert result["sharpe_ratio"] is not None


@pytest.mark.asyncio
async def test_performance_metrics_report_unavailable_when_no_evidence(monkeypatch):
    monkeypatch.setattr(learning, "get_bridge", lambda: FakeBridge())
    result = await learning.get_model_performance()

    assert result["prediction_count"] == 0
    assert result["accuracy_pct"] is None
    assert result["precision_macro_pct"] is None
    assert result["recall_macro_pct"] is None
    assert result["trade_count"] == 0
    assert result["profit_factor"] is None
    assert result["win_rate_pct"] is None
    assert result["max_drawdown_pct"] is None
    assert result["sharpe_ratio"] is None


@pytest.mark.asyncio
async def test_profit_factor_is_infinite_when_no_losses(monkeypatch):
    bridge = FakeBridge(
        trades=[
            {"closed_at": "2026-10-01T00:00:00+00:00", "pnl": 5.0},
            {"closed_at": "2026-10-02T00:00:00+00:00", "pnl": 10.0},
        ]
    )
    monkeypatch.setattr(learning, "get_bridge", lambda: bridge)
    result = await learning.get_model_performance()
    assert result["profit_factor"] == "infinite"
