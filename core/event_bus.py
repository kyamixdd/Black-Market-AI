"""BlackMarket Intelligence Bus.

Components communicate through structured events via asyncio.Queue.
Critical events are persisted to SQLite so they can be replayed after restart.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .event_models import Event

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self, maxsize: int = 4096):
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers: dict[str, list[Callable[[Event], Awaitable[None]]]] = {}
        self._running = False
        self._stopping = False
        self._persist: Callable[[Event], Awaitable[None]] | None = None
        self._dropped = 0

    def subscribe(self, event_type: str, handler: Callable[[Event], Awaitable[None]]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: Callable[[Event], Awaitable[None]]) -> None:
        self._subscribers.setdefault("*", []).append(handler)

    def set_persist(self, persist: Callable[[Event], Awaitable[None]]) -> None:
        self._persist = persist

    async def publish(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped += 1
            logger.warning("Event bus full, dropping event %s (total dropped %d)",
                           event.event_type, self._dropped)

    async def publish_many(self, events: list[Event]) -> None:
        for ev in events:
            await self.publish(ev)

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        while True:
            if self._stopping and self._queue.empty():
                break
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                if self._persist is not None:
                    await self._persist(event)
                handlers = list(self._subscribers.get(event.event_type, [])) + \
                    list(self._subscribers.get("*", []))
                for handler in handlers:
                    try:
                        await handler(event)
                    except Exception:
                        logger.exception("Handler %s failed for event %s",
                                         getattr(handler, "__name__", handler), event.event_type)
            finally:
                self._queue.task_done()
        self._running = False

    async def stop(self) -> None:
        self._stopping = True
        self._running = False
        await self._queue.join()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def dropped(self) -> int:
        return self._dropped