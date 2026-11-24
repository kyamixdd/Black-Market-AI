"""Regression tests for scanner universe rotation and learning model validation."""
import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from market.scanner import Scanner
from learning.live_service import LiveLearningService


class FakeCache:
    def __init__(self):
        self.items = [{"symbol": f"COIN{i}USDT", "volume_24h": 1000 - i} for i in range(7)]

    def get_market_tickers(self, market):
        return list(self.items)


class FakeRegistry:
    def is_eligible(self, symbol, market):
        return True

    def list_symbols(self, market=None):
        return [{"symbol": item["symbol"]} for item in FakeCache().items]


class FakeCandleManager:
    def __init__(self):
        self.calls = []

    async def collect_historical(self, *args, **kwargs):
        self.calls.append((args[3], args[4]))


class FakeIntelligence:
    def __init__(self):
        self.scanned = []

    async def run_prioritized_scan(self, pairs):
        self.scanned.extend(pairs)


@pytest.mark.asyncio
async def test_scanner_rotates_through_full_eligible_universe(monkeypatch):
    monkeypatch.setattr("config.SCAN_ALL_ELIGIBLE_SYMBOLS", True)
    monkeypatch.setattr("config.SCANNER_ANALYSIS_BATCH_SIZE", 3)
    monkeypatch.setattr("config.SCANNER_STREAM_SYMBOL_LIMIT", 3)
    monkeypatch.setattr("config.MAX_CONCURRENT_SCANS", 2)
    scanner = Scanner(
        event_bus=SimpleNamespace(), registry=FakeRegistry(), cache=FakeCache(),
        spot_client=object(), futures_client=object(),
        candle_manager=FakeCandleManager(), intelligence=FakeIntelligence(),
    )
    scanner.analysis_timeframes = ("1m", "5m")
    await scanner._analyze_market("SPOT")
    await scanner._analyze_market("SPOT")
    scanned = [symbol for _, symbol in scanner.intelligence.scanned]
    assert scanned == ["COIN0USDT", "COIN1USDT", "COIN2USDT", "COIN3USDT", "COIN4USDT", "COIN5USDT"]
    assert len(scanner.candle_manager.calls) == 12


@pytest.mark.asyncio
async def test_stream_handler_updates_only_originating_market(monkeypatch):
    monkeypatch.setattr("config.SCAN_ALL_ELIGIBLE_SYMBOLS", False)
    monkeypatch.setattr("config.SCANNER_ANALYSIS_BATCH_SIZE", 3)
    monkeypatch.setattr("config.SCANNER_STREAM_SYMBOL_LIMIT", 3)
    monkeypatch.setattr("config.MAX_CONCURRENT_SCANS", 2)
    class Cache:
        def __init__(self): self.updated = []
        def update_ticker(self, *args, **kwargs): self.updated.append(args)
        def get_market_tickers(self, market): return []
    cache = Cache()
    scanner = Scanner(SimpleNamespace(), FakeRegistry(), cache, object(), object())
    await scanner._stream_handler({"_market": "FUTURES", "data": {"s": "BTCUSDT", "c": "10", "q": "100", "P": "1"}})
    assert len(cache.updated) == 1
    assert cache.updated[0][0] == "FUTURES"


def test_river_model_requires_chronological_holdout_thresholds():
    service = object.__new__(LiveLearningService)
    rng = np.random.default_rng(7)
    X = rng.normal(size=(600, 36)).astype(np.float32)
    y = np.where(X[:, 0] > 0, 2, 0).astype(np.int32)
    result = service._train_validate_river(X, y)
    assert "metrics" in result
    assert result["metrics"]["holdout_samples"] > 0
    assert result["metrics"]["validation_method"] == "purged_chronological_80_20_frozen_holdout"
    assert result["metrics"]["holdout_untouched"] is True
    assert result["metrics"]["thresholds"]["accuracy_min"] == 0.52


def test_river_holdout_is_frozen_and_labels_never_update_candidate(monkeypatch):
    updates = []

    class FrozenCheckModel:
        def learn_one(self, features, label):
            updates.append(label)

        def predict_one(self, features):
            return 0

    class PipelineFactory:
        def __call__(self, *args):
            return FrozenCheckModel()

    monkeypatch.setattr("learning.live_service.compose.Pipeline", PipelineFactory())
    service = object.__new__(LiveLearningService)
    samples = 600
    X = np.zeros((samples, 36), dtype=np.float32)
    y = np.arange(samples, dtype=np.int32) % 2
    timestamps = np.arange(samples, dtype=np.int64) * 3_600_000
    result = service._train_validate_river(X, y, timestamps)
    assert result["metrics"]["holdout_untouched"] is True
    assert len(updates) == result["metrics"]["train_samples"]
    assert result["metrics"]["train_end_timestamp"] < result["metrics"]["holdout_start_timestamp"]


def test_learning_status_summary_preserves_validation_failure_details_without_oof_payloads():
    validation = {
        "promotion_gate": {
            "passes": False,
            "failure_reasons": ["no active champion comparison evidence"],
            "models": {"rf": {"passes": False, "mean_f1": 0.51, "mean_accuracy": 0.60,
                                "failure_reasons": ["mean F1 below required 0.500"]}},
            "criteria": {"min_mean_f1": 0.50},
            "economic_evidence": {"rf": {"net_expectancy": -0.001, "max_drawdown_pct": 95.0}},
            "validation_provenance": {"method": "purged_timestamp_walk_forward"},
        },
        "rf": {"out_of_fold": [{"index": i} for i in range(5000)],
               "aggregated": {"mean_accuracy": 0.60, "mean_f1": 0.51},
               "folds": [{"fold": 0, "test_size": 25, "f1_macro": 0.51}]},
    }

    summary = LiveLearningService._training_summary({
        "status": "validation_failed", "samples": 5688, "validation": validation,
    })

    assert summary["validation"]["promotion_gate"]["failure_reasons"] == ["no active champion comparison evidence"]
    assert summary["validation"]["promotion_gate"]["models"]["rf"]["mean_f1"] == 0.51
    assert summary["validation"]["promotion_gate"]["models"]["rf"]["economic_evidence"]["max_drawdown_pct"] == 95.0
    assert summary["validation"]["models"]["rf"]["folds"][0]["f1_macro"] == 0.51
    assert "out_of_fold" not in str(summary)



@pytest.mark.asyncio
async def test_autonomous_decisions_restore_signal_identity_from_event_envelope():
    from core.orchestrator import Orchestrator

    persisted = []
    sized_signals = []
    gate_signals = []
    orchestrator = object.__new__(Orchestrator)
    orchestrator.simulator = SimpleNamespace(
        get_balance=lambda _market: 500.0,
        _calculate_order_quantity=lambda signal, _balance: (
            sized_signals.append(dict(signal)) or (0.25, 1.0)
        ),
    )
    orchestrator.repo = SimpleNamespace(save_system_event=persisted.append)
    orchestrator.telegram = None
    orchestrator._autonomous_enabled = True
    def block_after_capture(signal):
        gate_signals.append(dict(signal))
        return False, "blocked_for_test"

    orchestrator._live_paper_confidence_gate = block_after_capture
    payload = {
        "signal_id": "envelope-market-signal",
        "direction": "LONG",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": [102.0],
        "confidence": 0.8,
        "reason": "test-rejected",
    }
    event = SimpleNamespace(payload=payload, symbol="BTCUSDT", market="SPOT")

    await orchestrator._on_signal_rejected(event)
    await orchestrator._on_signal_validated(event)

    assert len(persisted) == 2
    assert all(item["market"] == "SPOT" for item in persisted)
    assert all(item["symbol"] == "BTCUSDT" for item in persisted)
    assert all(item["payload"]["position_size"] == 0.25 for item in persisted)
    assert len(sized_signals) == 2
    assert all(item["market"] == "SPOT" for item in sized_signals)
    assert len(gate_signals) == 1
    assert gate_signals[0]["market"] == "SPOT"
    assert gate_signals[0]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_low_confidence_live_signal_cannot_open_paper_position(monkeypatch):
    from core.orchestrator import Orchestrator
    from unittest.mock import AsyncMock

    monkeypatch.setattr("core.orchestrator.PAPER_TRADING_ENABLED", True)
    orchestrator = object.__new__(Orchestrator)
    orchestrator.simulator = SimpleNamespace(execute_signal=AsyncMock())
    orchestrator.strategy_selector = SimpleNamespace(get_weight=lambda *_: 1.0)
    orchestrator.telegram = None
    orchestrator._autonomous_enabled = True
    orchestrator._record_autonomous_decision = lambda *_args, **_kwargs: None
    orchestrator._live_paper_confidence_gate = lambda _signal: (False, "below_historical_confidence_threshold")
    event = SimpleNamespace(payload={
        "signal_id": "low-confidence-signal",
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "strategy": "momentum",
        "regime": "TRENDING",
        "confidence": 0.62,
    })

    await orchestrator._on_signal_validated(event)

    orchestrator.simulator.execute_signal.assert_not_awaited()



@pytest.mark.asyncio
async def test_live_model_low_confidence_is_blocked_before_simulator_execution(monkeypatch):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock
    from core.orchestrator import Orchestrator

    monkeypatch.setattr("core.orchestrator.PAPER_TRADING_ENABLED", True)
    model_version = "20260101_000000"
    active_models = [
        SimpleNamespace(is_active=True, model_type="random_forest", version=f"random_forest_{model_version}"),
        SimpleNamespace(is_active=True, model_type="xgboost", version=f"xgboost_{model_version}"),
    ]
    historical = [
        SimpleNamespace(
            model_version=model_version, predicted_class="UP",
            confidence=0.90, actual_return_pct=1.0,
        )
        for _ in range(25)
    ]
    predictor = SimpleNamespace(
        is_trained=True, version=model_version,
        predict=lambda _features: {
            "predicted_class": "UP", "confidence": 0.49,
            "prob_up": 0.49, "prob_down": 0.30, "prob_flat": 0.21,
        },
    )
    orchestrator = object.__new__(Orchestrator)
    orchestrator.intelligence = SimpleNamespace(predictor=predictor)
    orchestrator.repo = SimpleNamespace(
        get_model_registry=lambda: active_models,
        get_predictions_history=lambda _limit: historical,
        save_prediction=lambda _prediction: None,
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    closed_candles = [
        {"close_time": now_ms - 1000, **{name: 1.0 for name in ("open", "high", "low", "close", "volume")}}
        for _ in range(50)
    ]
    orchestrator.cache = SimpleNamespace(get_snapshot=lambda *_args: {"timestamp": datetime.now(timezone.utc)})
    orchestrator.candle_manager = SimpleNamespace(
        get_series=lambda *_args, **_kwargs: closed_candles,
    )
    orchestrator.feature_engine = SimpleNamespace(
        build_features=lambda *_args, **_kwargs: np.zeros(36, dtype=np.float32),
    )
    orchestrator._confidence_threshold_cache = {}
    orchestrator.simulator = SimpleNamespace(execute_signal=AsyncMock())
    orchestrator.strategy_selector = SimpleNamespace(get_weight=lambda *_: 1.0)
    orchestrator.telegram = None
    orchestrator._autonomous_enabled = True
    orchestrator._record_autonomous_decision = lambda *_args, **_kwargs: None
    event = SimpleNamespace(payload={
        "signal_id": "model-low-confidence",
        "symbol": "BTCUSDT", "market": "SPOT",
        "strategy": "momentum", "regime": "TRENDING", "direction": "LONG",
        "confidence": 0.9,
    })

    allowed, reason = orchestrator._live_paper_confidence_gate(event.payload)
    assert not allowed
    assert reason == "below_historical_confidence_threshold"

    await orchestrator._on_signal_validated(event)
    orchestrator.simulator.execute_signal.assert_not_awaited()
