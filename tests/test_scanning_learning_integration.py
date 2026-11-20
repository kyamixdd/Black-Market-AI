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
        def update_ticker(self, *args): self.updated.append(args)
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
    assert result["metrics"]["validation_method"] == "chronological_80_20_prequential_holdout"
