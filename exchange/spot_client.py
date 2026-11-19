"""Binance Spot public REST client."""
from __future__ import annotations

import logging

from .base_client import BasePublicClient
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class SpotClient(BasePublicClient):
    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(rate_limiter, "https://data-api.binance.vision", "spot")

    async def get_klines(self, symbol: str, interval: str, start_ms: int | None = None,
                         end_ms: int | None = None, limit: int = 500) -> list[list]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return await self._get("/api/v3/klines", params)

    async def get_ticker_24h(self, symbol: str) -> dict:
        return await self._get("/api/v3/ticker/24hr", {"symbol": symbol})

    async def get_all_tickers(self) -> list[dict]:
        return await self._get("/api/v3/ticker/24hr")

    async def get_depth(self, symbol: str, limit: int = 20) -> dict:
        return await self._get("/api/v3/depth", {"symbol": symbol, "limit": limit})

    async def get_trades(self, symbol: str, limit: int = 100) -> list[dict]:
        return await self._get("/api/v3/trades", {"symbol": symbol, "limit": limit})

    async def get_aggregate_trades(self, symbol: str, limit: int = 1000) -> list[dict]:
        return await self._get("/api/v3/aggTrades", {"symbol": symbol, "limit": limit})

    async def get_exchange_info(self) -> dict:
        return await self._get("/api/v3/exchangeInfo")