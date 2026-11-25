"""Base public REST client with bounded retries and request concurrency."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import aiohttp

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BasePublicClient:
    def __init__(
        self,
        rate_limiter: RateLimiter,
        base_url: str,
        name: str,
        server_time_path: str | None = None,
    ):
        self.rate_limiter = rate_limiter
        self.base_url = base_url.rstrip("/")
        self.name = name
        self.server_time_path = server_time_path
        self._clock_offset_ms = 0
        self._clock_synced_at: float | None = None
        self._clock_sync_lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None
        self._request_slots = asyncio.Semaphore(8)
        self._max_retries = 3

    def now_ms(self) -> int:
        """Return the local epoch estimate corrected by the exchange clock offset."""
        return int(time.time() * 1000) + self._clock_offset_ms

    async def sync_clock_if_due(self, interval_seconds: float = 300.0) -> bool:
        """Refresh local-to-exchange clock offset, retaining the last good offset on failure."""
        if not self.server_time_path:
            return False
        async with self._clock_sync_lock:
            if (
                self._clock_synced_at is not None
                and time.monotonic() - self._clock_synced_at < interval_seconds
            ):
                return False
            before_ms = int(time.time() * 1000)
            try:
                response = await self._get(self.server_time_path, timeout=10.0)
                server_ms = int(response["serverTime"])
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, ValueError) as exc:
                logger.warning("%s exchange clock sync failed; retaining previous offset: %s", self.name, exc)
                self._clock_synced_at = time.monotonic()
                return False
            after_ms = int(time.time() * 1000)
            self._clock_offset_ms = server_ms - ((before_ms + after_ms) // 2)
            self._clock_synced_at = time.monotonic()
            if abs(self._clock_offset_ms) > 5_000:
                logger.warning(
                    "%s local clock differs from exchange by %.1fs; using exchange time for market-data checks",
                    self.name,
                    self._clock_offset_ms / 1000,
                )
            else:
                logger.info("%s exchange clock synchronized (offset %.3fs)", self.name, self._clock_offset_ms / 1000)
            return True

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
