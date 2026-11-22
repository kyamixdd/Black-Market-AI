"""Base public REST client with bounded retries and request concurrency."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import aiohttp

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BasePublicClient:
    def __init__(self, rate_limiter: RateLimiter, base_url: str, name: str):
        self.rate_limiter = rate_limiter
        self.base_url = base_url.rstrip("/")
        self.name = name
        self._session: aiohttp.ClientSession | None = None
        self._request_slots = asyncio.Semaphore(8)
        self._max_retries = 3

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=16, limit_per_host=8, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, path: str, params: dict | None, timeout: float,
                       raw: bool) -> Any:
        url = f"{self.base_url}{path}"
        session = await self._ensure_session()
        async with self._request_slots:
            for attempt in range(self._max_retries + 1):
                await self.rate_limiter.acquire(f"{self.name}_rest", 1.0, timeout=30.0)
                try:
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as resp:
                        if resp.status in (418, 429) or 500 <= resp.status <= 599:
                            if attempt >= self._max_retries:
                                resp.raise_for_status()
                            retry_after = resp.headers.get("Retry-After")
                            try:
                                delay = min(30.0, max(0.0, float(retry_after))) if retry_after else 0.0
                            except ValueError:
                                delay = 0.0
                            if delay == 0:
                                delay = min(8.0, 0.5 * (2 ** attempt) + random.uniform(0, 0.25))
                            logger.warning("%s REST %s returned %s; retry %d/%d in %.2fs",
                                           self.name, path, resp.status, attempt + 1,
                                           self._max_retries, delay)
                            await asyncio.sleep(delay)
                            continue
                        resp.raise_for_status()
                        return await resp.read() if raw else await resp.json()
                except asyncio.CancelledError:
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    if attempt >= self._max_retries:
                        raise
                    delay = min(8.0, 0.5 * (2 ** attempt) + random.uniform(0, 0.25))
                    logger.warning("%s REST connection failed for %s; retry %d/%d in %.2fs",
                                   self.name, path, attempt + 1, self._max_retries, delay)
                    await asyncio.sleep(delay)
        raise RuntimeError("REST retry loop exhausted")

    async def _get(self, path: str, params: dict | None = None,
                   timeout: float = 30.0) -> Any:
        return await self._request(path, params, timeout, raw=False)

    async def _get_raw(self, path: str, params: dict | None = None,
                       timeout: float = 30.0) -> bytes:
        return await self._request(path, params, timeout, raw=True)
