"""Binance USDⓈ-M Futures public REST client."""
from __future__ import annotations

import logging
from typing import Any

from .base_client import BasePublicClient
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class FuturesClient(BasePublicClient):
    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            rate_limiter, "https://fapi.binance.com", "futures",
            server_time_path="/fapi/v1/time",
        )

    async def get_klines(self, symbol: str, interval: str, start_ms: int | None = None,
                         end_ms: int | None = None, limit: int = 500) -> list[list]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return await self._get("/fapi/v1/klines", params)

    async def get_ticker_24h(self, symbol: str) -> dict:
        return await self._get("/fapi/v1/ticker/24hr", {"symbol": symbol})

    async def get_all_tickers(self) -> list[dict]:
        return await self._get("/fapi/v1/ticker/24hr")

    async def get_mark_price(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else {}
        return await self._get("/fapi/v1/premiumIndex", params)

    async def get_open_interest(self, symbol: str) -> dict:
        return await self._get("/fapi/v1/openInterest", {"symbol": symbol})

    async def get_global_long_short_account_ratio(
        self, symbol: str, period: str = "1h", limit: int = 24
    ) -> list[dict]:
        return await self._get(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": period, "limit": limit},
        )

    async def get_aggregate_trades(self, symbol: str, limit: int = 1000) -> list[dict]:
        return await self._get("/fapi/v1/aggTrades", {"symbol": symbol, "limit": limit})

    async def get_funding_rate_history(self, symbol: str, limit: int = 100) -> list[dict]:
        return await self._get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": limit})

    async def get_depth(self, symbol: str, limit: int = 20) -> dict:
        return await self._get("/fapi/v1/depth", {"symbol": symbol, "limit": limit})

    async def get_exchange_info(self) -> dict:
        return await self._get("/fapi/v1/exchangeInfo")