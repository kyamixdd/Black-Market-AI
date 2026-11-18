"""Candle aggregation and multi-timeframe alignment."""
from __future__ import annotations

import logging
import time
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)

# Timeframe in seconds
TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
    "8h": 28800, "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800,
}


class CandleManager:
    """Manages raw candles and builds aligned multi-timeframe series."""

    def __init__(self):
        self._candles: dict[tuple, list[dict]] = defaultdict(list)
        self._max_per_series = 250
        # Keep a bounded in-memory working set on low-memory desktop machines.
        self._max_series = 1800
        self._last_access: dict[tuple, float] = {}
        self._last_open_time: dict[tuple, int] = {}

    def _touch_series(self, key: tuple) -> None:
        if key not in self._candles and len(self._candles) >= self._max_series:
            oldest = min(self._last_access, key=self._last_access.get)
            self._candles.pop(oldest, None)
            self._last_access.pop(oldest, None)
            self._last_open_time.pop(oldest, None)
        self._last_access[key] = time.monotonic()

    def add_candle(self, market: str, symbol: str, timeframe: str,
                   open_time: int, open_: float, high: float, low: float,
                   close: float, volume: float, close_time: int | None = None) -> bool:
        """Add a candle, deduplicate by open_time. Returns True if added, False if duplicate."""
        key = (market, symbol, timeframe)

        candle = {
            "open_time": open_time, "open": open_, "high": high,
            "low": low, "close": close, "volume": volume,
            "close_time": close_time or open_time + TIMEFRAME_SECONDS.get(timeframe, 60) * 1000 - 1,
        }
        self._touch_series(key)
        series = self._candles[key]
        # REST refreshes overlap hundreds of previously fetched candles. Replace
        # matching timestamps instead of appending the same history repeatedly.
        for index, existing in enumerate(series):
            if existing["open_time"] == open_time:
                series[index] = candle
                self._last_open_time[key] = series[-1]["open_time"] if series else open_time
                return False

        # Keep the series ordered even when a backfill arrives out of order.
        if not series or open_time > series[-1]["open_time"]:
            series.append(candle)
        else:
            insert_at = next(
                (i for i, existing in enumerate(series) if existing["open_time"] > open_time),
                len(series),
            )
            series.insert(insert_at, candle)

        if len(series) > self._max_per_series:
            del series[:-self._max_per_series]
        self._last_open_time[key] = series[-1]["open_time"]
        return True

    def update_current_candle(self, market: str, symbol: str, timeframe: str,
                              open_time: int, open_: float, high: float, low: float,
                              close: float, volume: float, close_time: int | None = None) -> bool:
        """Replace the current unclosed candle when a REST refresh has newer values."""
        key = (market, symbol, timeframe)
        series = self._candles.get(key, [])
        if not series or series[-1]["open_time"] != open_time:
            return False
        self._last_access[key] = time.monotonic()
        series[-1] = {
            "open_time": open_time,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "close_time": close_time or open_time + TIMEFRAME_SECONDS.get(timeframe, 60) * 1000 - 1,
        }
        return True

    def detect_missing_candles(self, market: str, symbol: str, timeframe: str,
                                expected_count: int = 10) -> list[int]:
        """Detect missing candles by checking open_time gaps."""
        key = (market, symbol, timeframe)
        series = self._candles.get(key, [])
        if len(series) < 2:
            return []

        tf_seconds = TIMEFRAME_SECONDS.get(timeframe, 60)
        expected_interval_ms = tf_seconds * 1000
        missing = []

        # Compare adjacent candles from newest to oldest. The newer candle
        # must open exactly one timeframe after the older candle.
        for i in range(1, min(len(series), expected_count)):
            newer = series[-i]["open_time"]
            older = series[-(i + 1)]["open_time"]
            expected_time = older + expected_interval_ms
            if newer > expected_time:
                missing.extend(range(expected_time, newer, expected_interval_ms))

        return missing

    def get_series(self, market: str, symbol: str, timeframe: str, limit: int = 200) -> list[dict]:
        key = (market, symbol, timeframe)
        series = self._candles.get(key, [])
        if series:
            self._last_access[key] = time.monotonic()
        return series[-limit:] if series else []

    def get_closes(self, market: str, symbol: str, timeframe: str, limit: int = 200) -> np.ndarray:
        series = self.get_series(market, symbol, timeframe, limit)
        if not series:
            return np.array([])
        return np.array([c["close"] for c in series], dtype=float)

    def get_volumes(self, market: str, symbol: str, timeframe: str, limit: int = 200) -> np.ndarray:
        series = self.get_series(market, symbol, timeframe, limit)
        if not series:
            return np.array([])
        return np.array([c["volume"] for c in series], dtype=float)

    def get_highs(self, market: str, symbol: str, timeframe: str, limit: int = 200) -> np.ndarray:
        series = self.get_series(market, symbol, timeframe, limit)
        if not series:
            return np.array([])
        return np.array([c["high"] for c in series], dtype=float)

    def get_lows(self, market: str, symbol: str, timeframe: str, limit: int = 200) -> np.ndarray:
        series = self.get_series(market, symbol, timeframe, limit)
        if not series:
            return np.array([])
        return np.array([c["low"] for c in series], dtype=float)

    def get_ohlc(self, market: str, symbol: str, timeframe: str, limit: int = 200) -> dict:
        series = self.get_series(market, symbol, timeframe, limit)
        if not series:
            return {"open": np.array([]), "high": np.array([]), "low": np.array([]),
                    "close": np.array([]), "volume": np.array([])}
        return {
            "open": np.array([c["open"] for c in series], dtype=float),
            "high": np.array([c["high"] for c in series], dtype=float),
            "low": np.array([c["low"] for c in series], dtype=float),
            "close": np.array([c["close"] for c in series], dtype=float),
            "volume": np.array([c["volume"] for c in series], dtype=float),
        }

    def has_enough_data(self, market: str, symbol: str, timeframe: str, min_count: int = 50) -> bool:
        return len(self.get_series(market, symbol, timeframe)) >= min_count

    def clear(self) -> None:
        self._candles.clear()
        self._last_access.clear()
        self._last_open_time.clear()

    async def collect_historical(self, spot_client, futures_client, market: str, symbol: str,
                                  timeframe: str, limit: int = 500) -> int:
        """Collect historical candles from exchange and populate cache."""
        client = spot_client if market == "SPOT" else futures_client
        try:
            klines = await client.get_klines(symbol, timeframe, limit=limit)
            added = 0
            for k in klines:
                open_time = int(k[0])
                o = float(k[1])
                h = float(k[2])
                l = float(k[3])
                c = float(k[4])
                v = float(k[5])
                close_time = int(k[6])
                if self.add_candle(market, symbol, timeframe, open_time, o, h, l, c, v, close_time):
                    added += 1
                elif self.update_current_candle(market, symbol, timeframe, open_time, o, h, l, c, v, close_time):
                    added += 1
            return added
        except Exception as exc:
            logger.error("Historical collection failed for %s %s %s: %s", market, symbol, timeframe, exc)
            return 0