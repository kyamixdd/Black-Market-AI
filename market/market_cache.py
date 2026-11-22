"""In-memory market cache for fast access to latest prices, candles, and snapshots."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from collections import defaultdict

from .candle_manager import CandleManager


class MarketCache:
    def __init__(self):
        self._lock = threading.RLock()
        self._prices: dict[str, dict[str, float]] = defaultdict(dict)  # market -> symbol -> price
        self._volumes: dict[str, dict[str, float]] = defaultdict(dict)
        self._changes: dict[str, dict[str, float]] = defaultdict(dict)
        self._marks: dict[str, dict[str, float]] = defaultdict(dict)
        self._funding: dict[str, dict[str, float]] = defaultdict(dict)
        self._oi: dict[str, dict[str, float]] = defaultdict(dict)
        self._updated_at: dict[str, dict[str, datetime]] = defaultdict(dict)
        self._ticker_updated_at: dict[str, dict[str, datetime]] = defaultdict(dict)
        self._candle_manager = CandleManager()

    @property
    def candle_manager(self) -> CandleManager:
        return self._candle_manager

    def update_price(self, market: str, symbol: str, price: float) -> None:
        with self._lock:
            self._prices[market][symbol] = price

    def update_ticker(self, market: str, symbol: str, price: float, volume: float, change_pct: float) -> None:
        with self._lock:
            self._prices[market][symbol] = price
            self._volumes[market][symbol] = volume
            self._changes[market][symbol] = change_pct
            now = datetime.now(timezone.utc)
            self._updated_at[market][symbol] = now
            self._ticker_updated_at[market][symbol] = now

    def update_mark(self, market: str, symbol: str, mark: float, funding: float | None = None) -> None:
        with self._lock:
            self._marks[market][symbol] = mark
            if funding is not None:
                self._funding[market][symbol] = funding
            self._updated_at[market][symbol] = datetime.now(timezone.utc)

    def update_oi(self, market: str, symbol: str, oi: float) -> None:
        with self._lock:
            self._oi[market][symbol] = oi
            self._updated_at[market][symbol] = datetime.now(timezone.utc)

    def get_price(self, market: str, symbol: str) -> float | None:
        with self._lock:
            return self._prices.get(market, {}).get(symbol)

    def get_volume(self, market: str, symbol: str) -> float | None:
        with self._lock:
            return self._volumes.get(market, {}).get(symbol)

    def get_change(self, market: str, symbol: str) -> float | None:
        with self._lock:
            return self._changes.get(market, {}).get(symbol)

    def get_mark(self, market: str, symbol: str) -> float | None:
        with self._lock:
            return self._marks.get(market, {}).get(symbol)

    def get_funding(self, market: str, symbol: str) -> float | None:
        with self._lock:
            return self._funding.get(market, {}).get(symbol)

    def get_oi(self, market: str, symbol: str) -> float | None:
        with self._lock:
            return self._oi.get(market, {}).get(symbol)

    def get_snapshot(self, market: str, symbol: str) -> dict | None:
        with self._lock:
            price = self._prices.get(market, {}).get(symbol)
            if price is None:
                return None
            return {
                "symbol": symbol,
                "market": market,
                "timestamp": self._ticker_updated_at.get(market, {}).get(symbol),
                "price": price,
                "volume_24h": self._volumes.get(market, {}).get(symbol),
                "price_change_24h": self._changes.get(market, {}).get(symbol),
                "mark_price": self._marks.get(market, {}).get(symbol),
                "funding_rate": self._funding.get(market, {}).get(symbol),
                "open_interest": self._oi.get(market, {}).get(symbol),
                "bid_ask_spread": None,
                "orderbook_imbalance": None,
                "regime": "UNKNOWN",
            }

    def get_market_tickers(self, market: str) -> list[dict]:
        with self._lock:
            return [
                {
                    "symbol": symbol,
                    "market": market,
                    "timestamp": self._updated_at.get(market, {}).get(symbol),
                    "price": price,
                    "volume_24h": self._volumes.get(market, {}).get(symbol),
                    "price_change_24h": self._changes.get(market, {}).get(symbol),
                    "mark_price": self._marks.get(market, {}).get(symbol),
                    "funding_rate": self._funding.get(market, {}).get(symbol),
                    "open_interest": self._oi.get(market, {}).get(symbol),
                    "bid_ask_spread": None,
                    "orderbook_imbalance": None,
                    "regime": "UNKNOWN",
                }
                for symbol, price in self._prices.get(market, {}).items()
            ]


    def get_data_status(self, market: str, stale_after_seconds: float = 120.0) -> dict:
        """Return aggregate ticker freshness and source metadata."""
        with self._lock:
            timestamps = self._ticker_updated_at.get(market, {})
            if not timestamps:
                return {"market": market, "state": MarketDataState.UNAVAILABLE.value,
                        "last_success": None, "last_exchange_event": None,
                        "data_source": "NONE", "age_seconds": None}
            symbol, timestamp = max(timestamps.items(), key=lambda item: item[1])
            age = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
            state = (MarketDataState.STALE if age >= stale_after_seconds else
                     MarketDataState.DELAYED if age >= 30 else MarketDataState.LIVE)
            return {"market": market, "state": state.value,
                    "last_success": timestamp.isoformat(), "last_exchange_event": None,
                    "data_source": self._sources.get(market, {}).get(symbol, "UNKNOWN"),
                    "latest_symbol": symbol, "age_seconds": age}

    def top_movers(self, market: str, n: int = 20) -> list[tuple[str, float]]:
        with self._lock:
            items = list(self._changes.get(market, {}).items())
            items.sort(key=lambda kv: abs(kv[1]), reverse=True)
            return items[:n]