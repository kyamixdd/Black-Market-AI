"""Data Integrity Guardian: monitors market data quality and prevents signal generation on bad data."""
from __future__ import annotations

import logging
import time

import numpy as np
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
            self._update_status(market, symbol, "freshness", False, f"Missing {timeframe} candles")
            return False

        latest = series[-1]
        now_ms = int(time.time() * 1000)
        # For 1m candles, we expect data within last ~2 mins
        # For larger timeframes, we still expect the 'latest' completed candle to be recent
        delay_ms = now_ms - latest["close_time"]
        delay_sec = delay_ms / 1000

        # Exchange klines include the currently forming candle, whose close_time
        # is naturally in the future by up to one full timeframe.
        timeframe_ms = TIMEFRAME_SECONDS.get(timeframe, 60) * 1000
        if -delay_ms > timeframe_ms + self._max_clock_skew:
            self._update_status(market, symbol, "freshness", False, f"Future-dated {timeframe} candle")
            return False

        # Allow the timeframe duration plus a small exchange/network delay.
        is_fresh = delay_sec <= (TIMEFRAME_SECONDS.get(timeframe, 60) + self._max_freshness_delay)

        if not is_fresh:
            logger.warning("Data stale for %s %s %s: delay=%.1fs", market, symbol, timeframe, delay_sec)
        self._update_status(
            market, symbol, "freshness", is_fresh,
            None if is_fresh else f"Stale {timeframe} data",
        )
        return is_fresh

    def check_continuity(self, market: str, symbol: str, timeframe: str) -> bool:
        """Check for gaps in recent historical data."""
        missing = self.candles.detect_missing_candles(market, symbol, timeframe, expected_count=20)
        if missing:
            logger.warning("Data gap for %s %s %s: %d missing candles", market, symbol, timeframe, len(missing))
            self._update_status(market, symbol, "continuity", False, f"Gap in {timeframe} data")
            return False
        self._update_status(market, symbol, "continuity", True)
        return True

    def validate_ticker_consistency(self, market: str, symbol: str, ticker_price: float) -> bool:
        """Compare latest ticker price with last candle close."""
        # Check 1m timeframe for latest close
        series = self.candles.get_series(market, symbol, "1m", limit=1)
        if not series:
            self._update_status(market, symbol, "consistency", True)
            return True # Not enough data to compare

        last_close = series[-1]["close"]
        # Allow 2% discrepancy between WS ticker and last 1m close (arbitrary threshold)
        diff_pct = abs(ticker_price - last_close) / last_close
        if diff_pct > 0.02:
            logger.error("Ticker inconsistency for %s %s: ticker=%.4f, last_close=%.4f (%.2f%% diff)",
                         market, symbol, ticker_price, last_close, diff_pct * 100)
            self._update_status(market, symbol, "consistency", False, f"Ticker inconsistency: {diff_pct:.2%}")
            return False
        self._update_status(market, symbol, "consistency", True)
        return True

    def detect_anomalies(self, market: str, symbol: str, timeframe: str) -> bool:
        """Detect price anomalies using completed candles only."""
        now_ms = int(time.time() * 1000)
        series = [
            candle for candle in self.candles.get_series(market, symbol, timeframe, limit=30)
            if candle["close_time"] <= now_ms
        ]
        if len(series) < 20:
            self._update_status(market, symbol, "anomaly", True)
            return True

        highs = np.asarray([c["high"] for c in series], dtype=np.float64)
        lows = np.asarray([c["low"] for c in series], dtype=np.float64)
        closes = np.asarray([c["close"] for c in series], dtype=np.float64)
        from .volatility_analyzer import VolatilityAnalyzer
        last_atr = VolatilityAnalyzer.atr(highs, lows, closes, period=14)
        if last_atr <= 0:
            self._update_status(market, symbol, "anomaly", True)
            return True

        move = abs(closes[-1] - closes[-2])
        if move > last_atr * self._anomaly_threshold_atr:
            logger.error(
                "Price anomaly detected for %s %s %s: move=%.4f, atr=%.4f",
                market, symbol, timeframe, move, last_atr,
            )
            self._update_status(market, symbol, "anomaly", False, "Price spike detected")
            return False
        self._update_status(market, symbol, "anomaly", True)
        return True

    def is_symbol_valid(self, market: str, symbol: str) -> bool:
        """Determine if a symbol is valid for trading/signaling."""
        status = self._get_status(market, symbol)

        # Re-run checks before consulting the aggregate status so a symbol can
        # recover automatically after stale or incomplete candles are repaired.
        fresh_1m = self.validate_freshness(market, symbol, "1m")
        fresh_1h = self.validate_freshness(market, symbol, "1h")
        continuous_1m = self.check_continuity(market, symbol, "1m")
        continuous_1h = self.check_continuity(market, symbol, "1h")
        anomaly_free = self.detect_anomalies(market, symbol, "1h")
        status = self._get_status(market, symbol)
        return (
            fresh_1m and fresh_1h and continuous_1m and continuous_1h
            and anomaly_free and status.get("healthy", True)
        )

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
