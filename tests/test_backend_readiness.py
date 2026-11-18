"""Regression tests for backend readiness fixes."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

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


def test_health_endpoint_is_safe_before_first_exchange_websocket_message(monkeypatch):
    import asyncio

    from src_tauri.backend import main

    class FakeHealthMonitor:
        @staticmethod
        def get_status():
            return {"status": "OK", "metrics": {"uptime_seconds": 1.0}}

    class FakeOrchestrator:
        health_monitor = FakeHealthMonitor()
        scanner = SimpleNamespace(_running=True)

        @staticmethod
        def has_fresh_market_data():
            return True

    monkeypatch.setattr(main, "orchestrator", FakeOrchestrator())
    monkeypatch.setattr(main, "db", SimpleNamespace(health=lambda: {"status": "ok"}))
    monkeypatch.setattr(main, "ws_manager", SimpleNamespace(
        get_stats=lambda: {"running": True}
    ))

    response = asyncio.run(main.health_check())

    assert response["backend_ready"] is True
    assert response["market_data_active"] is True
    assert response["exchange_websocket_connected"] is False


@pytest.mark.asyncio
async def test_backend_startup_failure_closes_database(monkeypatch):
    from src_tauri.backend import main

    class FakeDB:
        closed = False

        def __init__(self, _url):
            pass

        def init_db(self):
            pass

        def integrity_check(self):
            return "ok"

        def close(self):
            self.closed = True

    fake_db = FakeDB("sqlite:///unused.db")

    class FailingOrchestrator:
        def __init__(self, _db):
            raise RuntimeError("simulated orchestrator startup failure")

    monkeypatch.setattr(main, "validate_config_or_exit", lambda: None)
    monkeypatch.setattr(main, "Database", lambda _url: fake_db)
    monkeypatch.setattr(main, "Repository", lambda _maker: SimpleNamespace(get_app_settings=lambda: {}))
    monkeypatch.setattr(main, "Orchestrator", FailingOrchestrator)

    with pytest.raises(RuntimeError, match="simulated orchestrator startup failure"):
        async with main.lifespan(main.app):
            pass

    assert fake_db.closed is True
    assert main.db is None


def test_persisted_settings_are_applied_before_service_construction(monkeypatch):
    from src_tauri.backend import main
    import config
    from core import orchestrator as orchestrator_module
    from intelligence import intelligence_core as intelligence_module
    from market import scanner as scanner_module
    from paper_trading import simulator as simulator_module

    for module, names in (
        (config, ("SPOT_ENABLED", "USDM_FUTURES_ENABLED", "TIMEFRAMES", "SPOT_INITIAL_BALANCE", "RISK_PER_TRADE_PCT")),
        (orchestrator_module, ("SPOT_ENABLED", "USDM_FUTURES_ENABLED", "TIMEFRAMES")),
        (scanner_module, ("SPOT_ENABLED", "USDM_FUTURES_ENABLED")),
        (intelligence_module, ("TIMEFRAMES",)),
        (simulator_module, ("SPOT_INITIAL_BALANCE", "RISK_PER_TRADE_PCT")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name))

    persisted = {
        "spot_enabled": False,
        "futures_enabled": True,
        "timeframes": ["1m", "5m", "1h"],
        "risk_per_trade_pct": 0.8,
        "spot_initial_balance": 300.0,
    }
    class FakeRepository:
        def __init__(self, _session_maker):
            pass

        @staticmethod
        def get_app_settings():
            return persisted

    monkeypatch.setattr(main, "Repository", FakeRepository)
    main._apply_persisted_settings(SimpleNamespace(session_maker=lambda: object()))

    assert config.SPOT_ENABLED is False
    assert orchestrator_module.SPOT_ENABLED is False
    assert scanner_module.SPOT_ENABLED is False
    assert config.TIMEFRAMES == ["1m", "5m", "1h"]
    assert orchestrator_module.TIMEFRAMES == ["1m", "5m", "1h"]
    assert intelligence_module.TIMEFRAMES == ["1m", "5m", "1h"]
    assert simulator_module.RISK_PER_TRADE_PCT == 0.8
    assert simulator_module.SPOT_INITIAL_BALANCE == 300.0
