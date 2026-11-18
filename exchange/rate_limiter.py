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
            if time.monotonic() >= deadline:
                raise TimeoutError("rate limiter timeout")
            await asyncio.sleep(0.05)


class RateLimiter:
    """Multi-bucket limiter used by REST and WebSocket managers."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}

    def bucket(self, name: str, rate: float) -> TokenBucket:
        if name not in self._buckets:
            self._buckets[name] = TokenBucket(rate)
        return self._buckets[name]

    async def acquire(self, name: str, tokens: float = 1.0, timeout: float = 30.0) -> None:
        await self.bucket(name, 60.0).acquire(tokens, timeout)