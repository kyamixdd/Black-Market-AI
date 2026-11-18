"""Base public REST client for Binance market data.

Only public endpoints are used. No order endpoints, no authentication.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BasePublicClient:
    def __init__(self, rate_limiter: RateLimiter, base_url: str, name: str):
        self.rate_limiter = rate_limiter
        self.base_url = base_url
        self.name = name
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get(self, path: str, params: dict | None = None,
                   timeout: float = 30.0) -> Any:
        await self.rate_limiter.acquire(f"{self.name}_rest", 1.0, timeout=30.0)
        url = f"{self.base_url}{path}"
        session = await self._ensure_session()
        async with session.get(url, params=params,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _get_raw(self, path: str, params: dict | None = None,
                       timeout: float = 30.0) -> bytes:
        await self.rate_limiter.acquire(f"{self.name}_rest", 1.0, timeout=30.0)
        url = f"{self.base_url}{path}"
        session = await self._ensure_session()
        async with session.get(url, params=params,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            resp.raise_for_status()
            return await resp.read()