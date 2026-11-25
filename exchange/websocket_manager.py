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


def _stream_url(base_url: str, streams: list[str]) -> str:
    """Build a Binance raw or combined stream URL from the endpoint base."""
    if len(streams) == 1:
        return f"{base_url}/ws/{streams[0]}"
    return f"{base_url}/stream?streams={'/'.join(streams)}"


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
        self._connected_by_market = {"SPOT": 0, "FUTURES": 0}
        self._last_message_ms: int | None = None
        self._last_message_by_market: dict[str, int | None] = {"SPOT": None, "FUTURES": None}
        self._reconnect_attempts = 0
        self._lifecycle_lock = asyncio.Lock()

    def add_handler(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handlers.append(handler)

    async def _run_stream(self, base_url: str, streams: list[str]) -> None:
        if not streams:
            return
        market = "SPOT" if base_url == SPOT_WS_URL else "FUTURES"
        url = _stream_url(base_url, streams)
        backoff = 1.0
        while self._running:
            try:
                await self.rate_limiter.acquire("websocket_conn", 1.0, timeout=30.0)
                logger.info("Connecting WS to %s (%d streams)", base_url, len(streams))
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    self._connected_connections += 1
                    self._connected_by_market[market] += 1
                    backoff = 1.0
                    logger.info("WebSocket connected for %s (%d streams)", market, len(streams))
                    try:
                        while self._running:
                            msg = await ws.recv()
                            try:
                                data = json.loads(msg)
                            except (TypeError, ValueError):
                                continue
                            if not isinstance(data, dict):
                                continue
                            message_time = int(time.time() * 1000)
                            self._last_message_ms = message_time
                            self._last_message_by_market[market] = message_time
                            data["_market"] = market
                            for handler in self._handlers:
                                try:
                                    await handler(data)
                                except Exception:
                                    logger.exception("WS handler failed")
                    finally:
                        self._connected_connections = max(0, self._connected_connections - 1)
                        self._connected_by_market[market] = max(
                            0, self._connected_by_market[market] - 1
                        )
                        if self._running:
                            logger.warning(
                                "WebSocket disconnected for %s; reconnecting",
                                market,
                            )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._reconnect_attempts += 1
                logger.warning("WS connection error on %s: %s (reconnecting in %.1fs)",
                               base_url, exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

    def _market_status(self, market: str) -> dict:
        streams = self._spot_streams if market == "SPOT" else self._futures_streams
        last_message_ms = self._last_message_by_market[market]
        age = (
            None if last_message_ms is None
            else max(0, int(time.time() * 1000) - last_message_ms)
        )
        if not self._running:
            state = "OFFLINE"
        elif not streams:
            state = "UNAVAILABLE"
        elif self._connected_by_market[market] > 0 and age is not None and age <= 120_000:
            state = "LIVE"
        elif self._connected_by_market[market] > 0:
            state = "STALE"
        else:
            state = "RECONNECTING"
        return {
            "state": state,
            "last_message_ms": last_message_ms,
            "message_age_ms": age,
            "connected_connections": self._connected_by_market[market],
            "active_streams": len(streams),
        }

    def status_snapshot(self) -> dict:
        markets = {market: self._market_status(market) for market in ("SPOT", "FUTURES")}
        configured = [status["state"] for status in markets.values() if status["active_streams"]]
        if not self._running:
            state = "OFFLINE"
        elif not configured:
            state = "UNAVAILABLE"
        elif all(value == "LIVE" for value in configured):
            state = "LIVE"
        elif any(value == "LIVE" for value in configured):
            state = "PARTIAL"
        elif any(value == "STALE" for value in configured):
            state = "STALE"
        else:
            state = "RECONNECTING"
        last_message_ms = max(
            (value for value in self._last_message_by_market.values() if value is not None),
            default=None,
        )
        age = (
            None if last_message_ms is None
            else max(0, int(time.time() * 1000) - last_message_ms)
        )
        return {
            "state": state,
            "last_message_ms": last_message_ms,
            "message_age_ms": age,
            "reconnect_attempts": self._reconnect_attempts,
            "active_streams": len(self._spot_streams) + len(self._futures_streams),
            "markets": markets,
        }

    async def start(self, spot_streams: list[str], futures_streams: list[str]) -> None:
        async with self._lifecycle_lock:
            if self._running:
                if spot_streams == self._spot_streams and futures_streams == self._futures_streams:
                    return
                await self._stop_unlocked()
            self._spot_streams = list(spot_streams)
            self._futures_streams = list(futures_streams)
            self._connected_connections = 0
            self._connected_by_market = {"SPOT": 0, "FUTURES": 0}
            self._last_message_ms = None
            self._last_message_by_market = {"SPOT": None, "FUTURES": None}
            self._running = True
            for base_url, streams in (
                (SPOT_WS_URL, self._spot_streams),
                (FUTURES_WS_URL, self._futures_streams),
            ):
                for i in range(0, len(streams), self.max_streams_per_conn):
                    chunk = streams[i : i + self.max_streams_per_conn]
                    if chunk:
                        self._tasks.append(asyncio.create_task(self._run_stream(base_url, chunk)))

    async def restart(self) -> None:
        """Restart active streams without leaving duplicate stream tasks behind."""
        spot_streams = list(self._spot_streams)
        futures_streams = list(self._futures_streams)
        await self.stop()
        await self.start(spot_streams, futures_streams)

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            await self._stop_unlocked()

    async def _stop_unlocked(self) -> None:
        self._running = False
        self._connected_connections = 0
        self._connected_by_market = {"SPOT": 0, "FUTURES": 0}
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
