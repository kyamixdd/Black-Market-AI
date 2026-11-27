"""Token-bucket rate limiter for Binance public endpoints."""
from __future__ import annotations

import asyncio
import time


class TokenBucket:
    def __init__(self, rate: float, capacity: int | None = None):
        self.rate = rate
        self.capacity = capacity or max(1, int(rate))
        self.tokens = float(self.capacity)
        self.last = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    async def acquire(self, tokens: float = 1.0, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while not self.consume(tokens):
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise TimeoutError("rate limiter timeout")
            deficit = max(0.0, tokens - self.tokens)
            wait_seconds = deficit / self.rate if self.rate > 0 else 0.05
            await asyncio.sleep(max(0.005, min(wait_seconds, remaining)))


class RateLimiter:
    """Multi-bucket limiter used by REST and WebSocket managers."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}

    def bucket(self, name: str, rate: float) -> TokenBucket:
        if name not in self._buckets:
            self._buckets[name] = TokenBucket(rate)
        return self._buckets[name]

    def update_used_weight(self, name: str, used_weight: int, limit: int = 1200) -> None:
        """Throttle a bucket when Binance X-MBX-USED-WEIGHT-1M approaches the limit."""
        if limit <= 0 or used_weight < int(limit * 0.8):
            return
        rate = 20.0 if name.startswith("spot") else 35.0 if name.startswith("futures") else 5.0
        bucket = self.bucket(name, rate)
        ratio = max(0.0, min(1.0, (limit - used_weight) / max(1.0, limit * 0.2)))
        bucket.tokens = min(bucket.tokens, bucket.capacity * ratio)

    async def acquire(self, name: str, tokens: float = 1.0, timeout: float = 30.0) -> None:
        rate = 20.0 if name.startswith("spot") else 35.0 if name.startswith("futures") else 5.0
        await self.bucket(name, rate).acquire(tokens, timeout)