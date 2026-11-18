"""Tests for Phase 14 Data Integrity and Market Validation."""
import time
import pytest
from market.candle_manager import CandleManager
from market.data_integrity import DataIntegrityGuardian
from intelligence.intelligence_core import IntelligenceCore
from core.event_bus import EventBus

class TestDataIntegrityGuardian:

    def test_freshness_check(self):
        cm = CandleManager()
        guardian = DataIntegrityGuardian(cm)

        # Add a fresh candle (1m timeframe)
        now_ms = int(time.time() * 1000)
        cm.add_candle("SPOT", "BTCUSDT", "1h", now_ms - 3600000, 50000, 50100, 49900, 50050, 10, close_time=now_ms - 1000)

        # Freshness for 1h candle with close_time 1 sec ago should be True
        assert guardian.validate_freshness("SPOT", "BTCUSDT", "1h") is True

        # Add a stale candle (close_time 4 hours ago for 1h candle)
        stale_time_ms = now_ms - (1000 * 3600 * 4)
        cm.add_candle("SPOT", "ETHUSDT", "1h", stale_time_ms - 3600000, 3000, 3010, 2990, 3005, 10, close_time=stale_time_ms)

        # Freshness should be False due to delay (> 3600 + 120s)
        assert guardian.validate_freshness("SPOT", "ETHUSDT", "1h") is False

    def test_continuity_gap_detection(self):
        cm = CandleManager()
        guardian = DataIntegrityGuardian(cm)

        base_time = 1000000
        tf_ms = 3600000  # 1h in ms

        # Add candles with a gap
        cm.add_candle("SPOT", "BTCUSDT", "1h", base_time, 50000, 50100, 49900, 50050, 10)
        cm.add_candle("SPOT", "BTCUSDT", "1h", base_time + tf_ms, 50050, 50200, 50000, 50150, 10)
        # Skip base_time + 2*tf_ms (GAP!)
        cm.add_candle("SPOT", "BTCUSDT", "1h", base_time + 3 * tf_ms, 50150, 50300, 50100, 50250, 10)

        # Gap detection should find the missing candle
        assert guardian.check_continuity("SPOT", "BTCUSDT", "1h") is False

    def test_ticker_consistency(self):
        cm = CandleManager()
        guardian = DataIntegrityGuardian(cm)

        now_ms = int(time.time() * 1000)
        cm.add_candle("SPOT", "BTCUSDT", "1m", now_ms - 60000, 50000, 50100, 49900, 50000, 10)

        # Consistent ticker price
        assert guardian.validate_ticker_consistency("SPOT", "BTCUSDT", 50100.0) is True

        # Inconsistent ticker price (>2% diff)
        assert guardian.validate_ticker_consistency("SPOT", "BTCUSDT", 55000.0) is False

    def test_price_anomaly_detection(self):
        cm = CandleManager()
        guardian = DataIntegrityGuardian(cm)

        base_time = 1000000
        tf_ms = 3600000

        # Build normal volatility series
        for i in range(20):
            cm.add_candle("SPOT", "BTCUSDT", "1h", base_time + i * tf_ms,
                          50000 + i * 10, 50100 + i * 10, 49900 + i * 10, 50050 + i * 10, 10)

        # Add a massive spike candle
        cm.add_candle("SPOT", "BTCUSDT", "1h", base_time + 20 * tf_ms,
                      50250, 60000, 50200, 60000, 100)

        # Should detect spike as an anomaly
        assert guardian.detect_anomalies("SPOT", "BTCUSDT", "1h") is False

    @pytest.mark.asyncio
    async def test_signal_blocked_on_invalid_data(self):
        event_bus = EventBus()
        cm = CandleManager()
        guardian = DataIntegrityGuardian(cm)
        intel = IntelligenceCore(event_bus, cm, guardian)

        # Explicitly mark symbol as unhealthy in guardian
        guardian._update_status("SPOT", "BTCUSDT", "manual_test", False, "Forced invalid")

        signals = await intel.analyze_symbol("BTCUSDT", "SPOT")
        assert len(signals) == 0  # Analysis skipped and empty list returned
