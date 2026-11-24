"""Symbol registry: tracks eligible instruments and their precision rules."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SymbolRegistry:
    def __init__(self):
        self._symbols: dict[str, dict] = {}  # key: "SPOT:BTCUSDT" -> info

    def register(self, symbol: str, market: str, info: dict) -> None:
        key = f"{market}:{symbol}"
        info.setdefault("symbol", symbol)
        info.setdefault("market", market)
        info.setdefault("is_eligible", True)
        info.setdefault("status", "TRADING")
        self._symbols[key] = info

    def get(self, symbol: str, market: str) -> dict | None:
        return self._symbols.get(f"{market}:{symbol}")

    def list_symbols(self, market: str | None = None) -> list[dict]:
        out = []
        for info in self._symbols.values():
            if market and info["market"] != market:
                continue
            if info.get("is_eligible") and info.get("status") == "TRADING":
                out.append(info)
        return out

    def is_eligible(self, symbol: str, market: str) -> bool:
        info = self.get(symbol, market)
        return bool(info and info.get("is_eligible") and info.get("status") == "TRADING")

    def count(self, market: str | None = None) -> int:
        return len(self.list_symbols(market))

    def refresh_eligibility(self, symbol: str, market: str, eligible: bool, status: str = "TRADING") -> None:
        info = self.get(symbol, market)
        if info:
            info["is_eligible"] = eligible
            info["status"] = status

    def to_dicts(self) -> list[dict]:
        out = []
        for info in self._symbols.values():
            if info.get("is_eligible") and info.get("status") == "TRADING":
                out.append({
                    "symbol": info["symbol"],
                    "market": info["market"],
                    "base_asset": info.get("base_asset", ""),
                    "quote_asset": info.get("quote_asset", ""),
                    "price_precision": info.get("price_precision", 4),
                    "quantity_precision": info.get("quantity_precision", 4),
                    "tick_size": info.get("tick_size", 0.0001),
                    "step_size": info.get("step_size", 0.0001),
                    "min_notional": info.get("min_notional", 10.0),
                    "status": info.get("status", "TRADING"),
                    "is_eligible": info.get("is_eligible", True),
                })
        return out