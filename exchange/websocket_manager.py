"""Binance WebSocket Connection and Subscription Manager.

Handles safe stream multiplexing, reconnection, rate limiting, and event distribution.
Supports Spot: wss://stream.binance.com:9443/ws
And Futures: wss://fstream.binance.com/ws
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

import websockets

from .rate_limiter import RateLimiter
from market.data_reliability import MarketDataState

logger = logging.getLogger(__name__)

SPOT_WS_URL = "wss://stream.binance.com:9443"
FUTURES_WS_URL = "wss://fstream.binance.com"


class WebSocketManager:
    def __init__(self, rate_limiter: RateLimiter, max_streams_per_conn: int = 100):
        self.rate_limiter = rate_limiter
        self.max_streams_per_conn = max_streams_per_conn
        self._handlers: list[Callable[[dict], Awaitable[None]]] = []
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._subscribed_streams: set[str] = set()
        self._spot_streams: list[str] = []
        self._futures_streams: list[str] = []
        self._connected_connections = 0
        self._last_message_ms: int | None = None
        self._reconnect_attempts = 0

    def add_handler(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handlers.append(handler)

    @staticmethod
    def _build_stream_url(base_url: str, streams: list[str]) -> str:
        """Build Binance raw or combined stream URL from the exchange host root."""
        if not streams:
            raise ValueError("At least one stream is required")
        if len(streams) == 1:
            return f"{base_url}/ws/{streams[0]}"
        stream_path = "/".join(streams)
        return f"{base_url}/stream?streams={stream_path}"

    async def _run_stream(self, base_url: str, streams: list[str]) -> None:
        if not streams:
            return
        url = self._build_stream_url(base_url, streams)
        backoff = 1.0
        while self._running:
            try:
                await self.rate_limiter.acquire("websocket_conn", 1.0, timeout=30.0)
                logger.info("Connecting WS to %s (%d streams)", base_url, len(streams))
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    self._connected_connections += 1
                    backoff = 1.0
                    while self._running:
                        msg = await ws.recv()
                        self._last_message_ms = int(time.time() * 1000)
                        try:
                            data = json.loads(msg)
                        except Exception:
                            continue
                        if isinstance(data, dict):
                            data["_market"] = "SPOT" if base_url == SPOT_WS_URL else "FUTURES"
                        for handler in self._handlers:
                            try:
                                await handler(data)
                            except Exception:
                                logger.exception("WS handler failed")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._connected_connections = max(0, self._connected_connections - 1)
                self._reconnect_attempts += 1
                logger.warning("WS connection error on %s: %s (reconnecting in %.1fs)",
                               base_url, exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

    def status_snapshot(self) -> dict:
        age = None if self._last_message_ms is None else max(0, int(time.time() * 1000) - self._last_message_ms)
        if not self._running:
            state = "OFFLINE"
        elif self._connected_connections > 0 and age is not None and age <= 120_000:
            state = "LIVE"
        elif self._connected_connections > 0:
            state = "STALE"
        else:
            state = "RECONNECTING" if self._tasks else "UNAVAILABLE"
        return {"state": state, "last_message_ms": self._last_message_ms,
                "message_age_ms": age, "reconnect_attempts": self._reconnect_attempts,
                "active_streams": len(self._spot_streams) + len(self._futures_streams)}

    async def start(self, spot_streams: list[str], futures_streams: list[str]) -> None:
        if self._running:
            if spot_streams == self._spot_streams and futures_streams == self._futures_streams:
                return
            await self.stop()
        self._spot_streams = list(spot_streams)
        self._futures_streams = list(futures_streams)
        self._running = True
        # Chunk spot streams
        for i in range(0, len(self._spot_streams), self.max_streams_per_conn):
            chunk = self._spot_streams[i : i + self.max_streams_per_conn]
            if chunk:
                t = asyncio.create_task(self._run_stream(SPOT_WS_URL, chunk))
                self._tasks.append(t)
        # Chunk futures streams
        for i in range(0, len(self._futures_streams), self.max_streams_per_conn):
            chunk = self._futures_streams[i : i + self.max_streams_per_conn]
            if chunk:
                t = asyncio.create_task(self._run_stream(FUTURES_WS_URL, chunk))
                self._tasks.append(t)

    async def restart(self) -> None:
        """Restart active streams without leaving duplicate stream tasks behind."""
        spot_streams = list(self._spot_streams)
        futures_streams = list(self._futures_streams)
        await self.stop()
        await self.start(spot_streams, futures_streams)

    async def stop(self) -> None:
        self._running = False
        self._connected_connections = 0
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()