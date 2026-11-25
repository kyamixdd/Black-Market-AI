"""Shared market-data validation, freshness state, and bounded TTL cache primitives."""
from __future__ import annotations

import math
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Any

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,30}$")


class MarketDataState(str, Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    RECONNECTING = "RECONNECTING"
    OFFLINE = "OFFLINE"
    UNAVAILABLE = "UNAVAILABLE"


def valid_symbol(symbol: Any) -> bool:
    return isinstance(symbol, str) and bool(_SYMBOL_RE.fullmatch(symbol))


def valid_price(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except (TypeError, ValueError, OverflowError):
        return False


def valid_volume(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number >= 0
    except (TypeError, ValueError, OverflowError):
        return False


def validate_candle(open_time: Any, open_: Any, high: Any, low: Any, close: Any,
                    volume: Any, close_time: Any, now_ms: int | None = None,
                    max_future_skew_ms: int = 5_000) -> bool:
    try:
        ot, ct = int(open_time), int(close_time)
        o, h, l, c, v = map(float, (open_, high, low, close, volume))
    except (TypeError, ValueError, OverflowError):
        return False
    now = int(time.time() * 1000) if now_ms is None else now_ms
    if (
        ot <= 0
        or ct < ot
        or ot > now + max_future_skew_ms
        or ct > now
    ):
        return False
    if not all(math.isfinite(x) for x in (o, h, l, c, v)):
        return False
    if min(o, h, l, c) <= 0 or v < 0:
        return False
    return h >= max(o, c, l) and l <= min(o, c, h)


@dataclass(frozen=True)
class MarketDataStatus:
    state: MarketDataState
    source: str
    last_success_ms: int | None
    last_exchange_event_ms: int | None
    age_ms: int | None
    detail: str | None = None


class MarketDataHealth:
    """Track source timestamps and expose a stable freshness status contract."""
    def __init__(self, stale_after_ms: int = 120_000, delayed_after_ms: int = 30_000):
        self.stale_after_ms = max(1, stale_after_ms)
        self.delayed_after_ms = min(self.stale_after_ms, max(1, delayed_after_ms))
        self._source = "none"
        self._last_success_ms: int | None = None
        self._last_exchange_ms: int | None = None
        self._connection = MarketDataState.UNAVAILABLE
        self._detail: str | None = None

    def mark_success(self, source: str, exchange_event_ms: int | None = None,
                      received_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if received_ms is None else received_ms
        self._source = source
        self._last_success_ms = now
        if exchange_event_ms is not None and exchange_event_ms > 0:
            self._last_exchange_ms = exchange_event_ms
        self._connection = MarketDataState.LIVE
        self._detail = None

    def set_connection(self, state: MarketDataState, detail: str | None = None) -> None:
        self._connection = state
        self._detail = detail

    def snapshot(self, now_ms: int | None = None) -> MarketDataStatus:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        age = None if self._last_success_ms is None else max(0, now - self._last_success_ms)
        if self._connection in (MarketDataState.RECONNECTING, MarketDataState.OFFLINE):
            state = self._connection
        elif age is None:
            state = MarketDataState.UNAVAILABLE
        elif age >= self.stale_after_ms:
            state = MarketDataState.STALE
        elif age >= self.delayed_after_ms:
            state = MarketDataState.DELAYED
        else:
            state = MarketDataState.LIVE
        return MarketDataStatus(state, self._source, self._last_success_ms,
                                self._last_exchange_ms, age, self._detail)


class TTLCache:
    """Small LRU/TTL cache; expired entries are never returned."""
    def __init__(self, max_entries: int = 512, ttl_seconds: float = 5.0):
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(0.01, float(ttl_seconds))
        self._items: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def get(self, key: Any, now: float | None = None) -> Any | None:
        current = time.monotonic() if now is None else now
        item = self._items.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= current:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: Any, value: Any, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        self._items[key] = (current + self.ttl_seconds, value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)
