"""Binance WebSocket Connection and Subscription Manager.

Handles safe stream multiplexing, reconnection, rate limiting, and event distribution.
Supports Spot: wss://data-stream.binance.vision/ws
And Futures: wss://fstream.binance.com/ws
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import websockets

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

SPOT_WS_URL = "wss://stream.binance.com:9443/ws"
FUTURES_WS_URL = "wss://fstream.binance.com/ws"


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
        self._connected_streams: set[tuple[str, tuple[str, ...]]] = set()

    def add_handler(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handlers.append(handler)

    async def _run_stream(self, base_url: str, streams: list[str], market: str) -> None:
        if not streams:
            return
        stream_path = "/".join(streams)
        combined_base = base_url.removesuffix("/ws")
        url = f"{base_url}/{streams[0]}" if len(streams) == 1 else f"{combined_base}/stream?streams={stream_path}"
        backoff = 1.0
        while self._running:
            try:
                await self.rate_limiter.acquire("websocket_conn", 1.0, timeout=30.0)
                logger.info("Connecting WS to %s (%d streams)", base_url, len(streams))
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    connection_key = (market, tuple(streams))
                    self._connected_streams.add(connection_key)
                    backoff = 1.0
                    try:
                        while self._running:
                            msg = await ws.recv()
                            try:
                                data = json.loads(msg)
                            except Exception:
                                continue
                            if isinstance(data, dict):
                                data["_market"] = market
                            for handler in self._handlers:
                                try:
                                    await handler(data)
                                except Exception:
                                    logger.exception("WS handler failed")
                    finally:
                        self._connected_streams.discard(connection_key)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("WS connection error on %s: %s (reconnecting in %.1fs)",
                               base_url, exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

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
                t = asyncio.create_task(self._run_stream(SPOT_WS_URL, chunk, "SPOT"))
                self._tasks.append(t)
        # Chunk futures streams
        for i in range(0, len(self._futures_streams), self.max_streams_per_conn):
            chunk = self._futures_streams[i : i + self.max_streams_per_conn]
            if chunk:
                t = asyncio.create_task(self._run_stream(FUTURES_WS_URL, chunk, "FUTURES"))
                self._tasks.append(t)

    @property
    def connected(self) -> bool:
        """Whether at least one exchange stream is currently connected."""
        return bool(self._connected_streams)

    async def restart(self) -> None:
        """Restart active streams without leaving duplicate stream tasks behind."""
        spot_streams = list(self._spot_streams)
        futures_streams = list(self._futures_streams)
        await self.stop()
        await self.start(spot_streams, futures_streams)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()