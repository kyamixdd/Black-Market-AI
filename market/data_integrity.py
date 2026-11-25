"""Data Integrity Guardian: monitors market data quality and prevents signal generation on bad data."""
from __future__ import annotations

import logging
import time
from typing import Any

from .candle_manager import CandleManager, TIMEFRAME_SECONDS

logger = logging.getLogger(__name__)


class DataIntegrityGuardian:
    """Guardian for market data quality and connection reliability."""

    def __init__(self, candle_manager: CandleManager):
        self.candles = candle_manager
        # (market, symbol) -> dict of status
        self._symbol_status: dict[tuple[str, str], dict[str, Any]] = {}
        self._max_freshness_delay = 120  # 2 minutes for any timeframe to be considered stale
        self._max_clock_skew = 5000  # 5 seconds in ms
        self._anomaly_threshold_atr = 5.0  # 5x ATR is an anomaly

    def validate_freshness(self, market: str, symbol: str, timeframe: str) -> bool:
        """Check if the latest candle for a symbol is fresh."""
        series = self.candles.get_series(market, symbol, timeframe, limit=1)
        if not series:
            return False

        latest = series[-1]
        now_ms = self.candles.current_time_ms()
        # For 1m candles, we expect data within last ~2 mins
        # For larger timeframes, we still expect the 'latest' completed candle to be recent
        delay_sec = (now_ms - latest["close_time"]) / 1000

        # We use a relaxed threshold because some symbols update less frequently
        is_fresh = delay_sec < (TIMEFRAME_SECONDS.get(timeframe, 60) + self._max_freshness_delay)

        if not is_fresh:
            logger.warning("Data stale for %s %s %s: delay=%.1fs", market, symbol, timeframe, delay_sec)
            self._update_status(market, symbol, "freshness", False, f"Stale {timeframe} data")

        return is_fresh

    def check_continuity(self, market: str, symbol: str, timeframe: str) -> bool:
        """Check for gaps in recent historical data."""
        missing = self.candles.detect_missing_candles(market, symbol, timeframe, expected_count=20)
        if missing:
            logger.warning("Data gap for %s %s %s: %d missing candles", market, symbol, timeframe, len(missing))
            self._update_status(market, symbol, "continuity", False, f"Gap in {timeframe} data")
            return False
        return True

    def validate_ticker_consistency(self, market: str, symbol: str, ticker_price: float) -> bool:
        """Compare latest ticker price with last candle close."""
        # Check 1m timeframe for latest close
        series = self.candles.get_series(market, symbol, "1m", limit=1)
        if not series:
            return True # Not enough data to compare

        last_close = series[-1]["close"]
        # Allow 2% discrepancy between WS ticker and last 1m close (arbitrary threshold)
        diff_pct = abs(ticker_price - last_close) / last_close
        if diff_pct > 0.02:
            logger.error("Ticker inconsistency for %s %s: ticker=%.4f, last_close=%.4f (%.2f%% diff)",
                         market, symbol, ticker_price, last_close, diff_pct * 100)
            self._update_status(market, symbol, "consistency", False, f"Ticker inconsistency: {diff_pct:.2%}")
            return False
        return True

    def detect_anomalies(self, market: str, symbol: str, timeframe: str) -> bool:
        """Detect price anomalies using ATR."""
        ohlc = self.candles.get_ohlc(market, symbol, timeframe, limit=30)
        if len(ohlc["close"]) < 20:
            return True # Not enough data for ATR

        from .volatility_analyzer import VolatilityAnalyzer
        last_atr = VolatilityAnalyzer.atr(ohlc["high"], ohlc["low"], ohlc["close"], period=14)
        if last_atr == 0:
            return True

        last_close = ohlc["close"][-1]
        prev_close = ohlc["close"][-2]

        move = abs(last_close - prev_close)
        if last_atr > 0 and move > (last_atr * self._anomaly_threshold_atr):
            logger.error("Price anomaly detected for %s %s %s: move=%.4f, atr=%.4f",
                         market, symbol, timeframe, move, last_atr)
            self._update_status(market, symbol, "anomaly", False, "Price spike detected")
            return False
        return True

    def is_symbol_valid(self, market: str, symbol: str) -> bool:
        """Determine if a symbol is valid for trading/signaling."""
        status = self._get_status(market, symbol)

        # Check if any health flag is False
        if not status.get("healthy", True):
            return False

        # Perform freshness check on primary timeframe (1h)
        if not self.validate_freshness(market, symbol, "1h"):
            return False

        # Perform continuity check on primary timeframe (1h)
        if not self.check_continuity(market, symbol, "1h"):
            return False

        return True

    def _update_status(self, market: str, symbol: str, check_type: str,
                        is_healthy: bool, message: str | None = None) -> None:
        key = (market, symbol)
        if key not in self._symbol_status:
            self._symbol_status[key] = {"healthy": True, "checks": {}}

        self._symbol_status[key]["checks"][check_type] = {
            "healthy": is_healthy,
            "message": message,
            "timestamp": time.time()
        }

        # Recalculate overall health
        all_checks = self._symbol_status[key]["checks"].values()
        self._symbol_status[key]["healthy"] = all_checks and all(c["healthy"] for c in all_checks)

    def _get_status(self, market: str, symbol: str) -> dict[str, Any]:
        return self._symbol_status.get((market, symbol), {"healthy": True, "checks": {}})

    def reset_status(self, market: str, symbol: str) -> None:
        """Reset integrity status for a symbol (e.g. after successful resync)."""
        self._symbol_status.pop((market, symbol), None)
