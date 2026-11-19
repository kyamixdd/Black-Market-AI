"""Market discovery engine.

Fetches Binance exchange information (public REST) and builds the symbol registry.
No API keys required - only public market data.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .rate_limiter import RateLimiter
from .symbol_registry import SymbolRegistry

logger = logging.getLogger(__name__)

SPOT_EXCHANGE_INFO = "https://data-api.binance.vision/api/v3/exchangeInfo"
FUTURES_EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"


class MarketDiscovery:
    def __init__(self, registry: SymbolRegistry, rate_limiter: RateLimiter,
                 spot_enabled: bool = True, futures_enabled: bool = True):
        self.registry = registry
        self.rate_limiter = rate_limiter
        self.spot_enabled = spot_enabled
        self.futures_enabled = futures_enabled

    async def _fetch(self, url: str) -> dict[str, Any]:
        await self.rate_limiter.acquire("exchange_info", 1.0, timeout=30.0)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def discover_spot(self) -> int:
        if not self.spot_enabled:
            return 0
        try:
            data = await self._fetch(SPOT_EXCHANGE_INFO)
        except Exception as exc:
            logger.error("Spot exchange info failed: %s", exc)
            return 0
        count = 0
        for s in data.get("symbols", []):
            if s.get("status") != "TRADING":
                continue
            filters = {f["filterType"]: f for f in s.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            price = filters.get("PRICE_FILTER", {})
            min_notional = filters.get("MIN_NOTIONAL", {})
            info = {
                "symbol": s["symbol"],
                "market": "SPOT",
                "base_asset": s.get("baseAsset", ""),
                "quote_asset": s.get("quoteAsset", ""),
                "price_precision": s.get("pricePrecision", 4),
                "quantity_precision": s.get("quantityPrecision", 4),
                "tick_size": float(price.get("tickSize", 0.0001)),
                "step_size": float(lot.get("stepSize", 0.0001)),
                "min_notional": float(min_notional.get("minNotional", 10.0)),
                "status": s.get("status", "TRADING"),
                "is_eligible": True,
            }
            self.registry.register(s["symbol"], "SPOT", info)
            count += 1
        logger.info("Discovered %d spot symbols", count)
        return count

    async def discover_futures(self) -> int:
        if not self.futures_enabled:
            return 0
        try:
            data = await self._fetch(FUTURES_EXCHANGE_INFO)
        except Exception as exc:
            logger.error("Futures exchange info failed: %s", exc)
            return 0
        count = 0
        for s in data.get("symbols", []):
            if s.get("status") != "TRADING":
                continue
            filters = {f["filterType"]: f for f in s.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            price = filters.get("PRICE_FILTER", {})
            min_notional = filters.get("MIN_NOTIONAL", {})
            info = {
                "symbol": s["symbol"],
                "market": "FUTURES",
                "base_asset": s.get("baseAsset", ""),
                "quote_asset": s.get("quoteAsset", ""),
                "price_precision": s.get("pricePrecision", 4),
                "quantity_precision": s.get("quantityPrecision", 4),
                "tick_size": float(price.get("tickSize", 0.0001)),
                "step_size": float(lot.get("stepSize", 0.0001)),
                "min_notional": float(min_notional.get("minNotional", 10.0)),
                "status": s.get("status", "TRADING"),
                "is_eligible": True,
            }
            self.registry.register(s["symbol"], "FUTURES", info)
            count += 1
        logger.info("Discovered %d futures contracts", count)
        return count

    async def discover_all(self) -> dict[str, int]:
        spot = await self.discover_spot()
        futures = await self.discover_futures()
        return {"spot": spot, "futures": futures}