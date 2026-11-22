"""Candle aggregation and multi-timeframe alignment."""
from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np

from market.data_reliability import valid_symbol, validate_candle

logger = logging.getLogger(__name__)

# Timeframe in seconds
TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800,
}


class CandleManager:
    """Manages raw candles and builds aligned multi-timeframe series."""

    def __init__(self):
        self._candles: dict[tuple, list[dict]] = defaultdict(list)
        self._max_per_series = 500

    @staticmethod
    def _find_candle_index(series: list[dict], open_time: int) -> int:
        """Find the sorted insertion point for an open timestamp."""
        low = 0
        high = len(series)
        while low < high:
            middle = (low + high) // 2
            if series[middle]["open_time"] < open_time:
                low = middle + 1
            else:
                high = middle
        return low

    def add_candle(self, market: str, symbol: str, timeframe: str,
                   open_time: int, open_: float, high: float, low: float,
                   close: float, volume: float, close_time: int | None = None) -> bool:
        """Add a candle, deduplicate by open_time. Returns True if added, False if duplicate."""
        if market not in {"SPOT", "FUTURES"} or not valid_symbol(symbol) or timeframe not in TIMEFRAME_SECONDS:
            return False
        effective_close_time = close_time if close_time is not None else open_time + TIMEFRAME_SECONDS[timeframe] * 1000 - 1
        if not validate_candle(open_time, open_, high, low, close, volume, effective_close_time):
            return False

        key = (market, symbol, timeframe)
        series = self._candles[key]
        index = self._find_candle_index(series, open_time)
        if index < len(series) and series[index]["open_time"] == open_time:
            return False

        candle = {
            "open_time": open_time, "open": open_, "high": high,
            "low": low, "close": close, "volume": volume,
            "close_time": effective_close_time,
        }
        series.insert(index, candle)

        if len(series) > self._max_per_series:
            del series[:-self._max_per_series]
        return True

    def update_current_candle(self, market: str, symbol: str, timeframe: str,
                              open_time: int, open_: float, high: float, low: float,
                              close: float, volume: float, close_time: int | None = None) -> bool:
        """Replace the current unclosed candle when a REST refresh has newer values."""
        if market not in {"SPOT", "FUTURES"} or not valid_symbol(symbol) or timeframe not in TIMEFRAME_SECONDS:
            return False
        effective_close_time = close_time if close_time is not None else open_time + TIMEFRAME_SECONDS[timeframe] * 1000 - 1
        if not validate_candle(open_time, open_, high, low, close, volume, effective_close_time):
            return False
        key = (market, symbol, timeframe)
        series = self._candles.get(key, [])
        index = self._find_candle_index(series, open_time)
        if index >= len(series) or series[index]["open_time"] != open_time:
            return False
        if effective_close_time < series[index]["close_time"]:
            return False
        series[index] = {
            "open_time": open_time,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "close_time": effective_close_time,
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
        recent = series[-max(2, expected_count):]
        for previous, current in zip(recent, recent[1:]):
            gap = current["open_time"] - previous["open_time"]
            if gap > expected_interval_ms:
                missing.extend(range(previous["open_time"] + expected_interval_ms,
                                    current["open_time"], expected_interval_ms))

        return missing

    def get_series(self, market: str, symbol: str, timeframe: str, limit: int = 200) -> list[dict]:
        key = (market, symbol, timeframe)
        series = self._candles.get(key, [])
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
