"""Tests for measured market volatility and market-data freshness."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src_tauri.backend.bridge.orchestrator_bridge import OrchestratorBridge


def test_market_snapshot_freshness_thresholds():
    now = datetime.now(timezone.utc)
    live = OrchestratorBridge._with_freshness({"timestamp": now - timedelta(seconds=20)})
    delayed = OrchestratorBridge._with_freshness({"timestamp": now - timedelta(seconds=180)})
    stale = OrchestratorBridge._with_freshness({"timestamp": now - timedelta(seconds=600)})
    unknown = OrchestratorBridge._with_freshness({"timestamp": None})
    assert live["data_freshness"] == "LIVE"
    assert delayed["data_freshness"] == "DELAYED"
    assert stale["data_freshness"] == "STALE"
    assert unknown["data_freshness"] == "UNKNOWN"


def test_volatility_uses_hourly_returns_and_true_range():
    bridge = OrchestratorBridge.__new__(OrchestratorBridge)
    rows = []
    for index in range(25):
        close = 100 + index
        rows.append({
            "open_time": index * 3_600_000, "open": close - 0.5,
            "high": close + 1, "low": close - 1, "close": close,
            "volume": 10, "close_time": (index + 1) * 3_600_000 - 1,
        })
    bridge.candles = SimpleNamespace(get_series=lambda *args, **kwargs: rows)
    volatility, atr_pct = bridge._volatility_metrics("SPOT", "BTCUSDT")
    assert volatility is not None and volatility > 0
    assert atr_pct is not None and atr_pct > 0


def test_volatility_is_unavailable_without_enough_candles():
    bridge = OrchestratorBridge.__new__(OrchestratorBridge)
    bridge.candles = SimpleNamespace(get_series=lambda *args, **kwargs: [])
    assert bridge._volatility_metrics("SPOT", "BTCUSDT") == (None, None)


@pytest.mark.asyncio
async def test_volume_comparison_uses_completed_daily_quote_volume(monkeypatch):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    daily = []
    for index in range(8):
        close_time = now_ms - (8 - index) * 86_400_000
        daily.append([0, "1", "1", "1", "1", "1", close_time, "1000"])
    daily.append([0, "1", "1", "1", "1", "1", now_ms + 86_400_000, "9999"])
    client = SimpleNamespace(
        get_aggregate_trades=lambda *args, **kwargs: _async_value([
            {"p": "10", "q": "2", "m": False, "T": now_ms},
            {"p": "10", "q": "1", "m": True, "T": now_ms},
        ]),
        get_ticker_24h=lambda *args, **kwargs: _async_value({"quoteVolume": "1500"}),
        get_klines=lambda *args, **kwargs: _async_value(daily),
    )
    bridge = OrchestratorBridge.__new__(OrchestratorBridge)
    bridge.orch = SimpleNamespace(spot_client=client, futures_client=client)
    bridge._analytics_cache = {}
    result = await bridge.get_volume_stats("BTCUSDT", "SPOT")
    assert result["average_daily_quote_volume_7d"] == 1000
    assert result["volume_change_vs_7d_avg_pct"] == 50
    assert result["buy_volume"] == 20
    assert result["sell_volume"] == 10
    assert "not full 24h" in result["flow_sample_scope"]


async def _async_value(value):
    return value
