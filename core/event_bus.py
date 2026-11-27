"""BlackMarket Intelligence Bus.

Components communicate through structured events via asyncio.Queue.
Critical events are persisted to SQLite so they can be replayed after restart.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .event_models import Event
from .observability import log_event

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

    def unsubscribe_all(self, handler: Callable[[Event], Awaitable[None]]) -> None:
        """Remove a handler from wildcard and typed subscriptions."""
        for event_type, handlers in list(self._subscribers.items()):
            while handler in handlers:
                handlers.remove(handler)
            if not handlers:
                self._subscribers.pop(event_type, None)

    def set_persist(self, persist: Callable[[Event], Awaitable[None]]) -> None:
        self._persist = persist

    async def publish(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped += 1
            logger.warning("Event bus full, dropping event %s (total dropped %d)",
                           event.event_type, self._dropped)
            log_event(
                logger, logging.ERROR, "event_bus_queue_overflow",
                component="event_bus", operation="publish",
                outcome="DROPPED", event_type=event.event_type,
                failed_count=self._dropped,
                recommendation="Inspect slow event subscribers and database persistence latency; increase queue capacity only after identifying the bottleneck.",
            )

    async def publish_many(self, events: list[Event]) -> None:
        for ev in events:
            await self.publish(ev)

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        log_event(
            logger, logging.INFO, "event_bus_started",
            component="event_bus", operation="run",
            outcome="SUCCESS", queue_capacity=self._queue.maxsize,
        )
        while True:
            if self._stopping and self._queue.empty():
                break
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                if self._persist is not None:
                    try:
                        await self._persist(event)
                    except Exception as exc:
                        logger.exception("Event persistence failed for event %s", event.event_type)
                        log_event(
                            logger, logging.ERROR, "event_persist_failed",
                            component="event_bus", operation="persist",
                            outcome="FAILURE", event_type=event.event_type,
                            exception_type=type(exc).__name__,
                            recommendation="Inspect database persistence health; event dispatch continues.",
                        )
                handlers = list(self._subscribers.get(event.event_type, [])) + \
                    list(self._subscribers.get("*", []))
                for handler in handlers:
                    try:
                        await handler(event)
                    except Exception as exc:
                        logger.exception("Handler %s failed for event %s",
                                         getattr(handler, "__name__", handler), event.event_type)
                        log_event(
                            logger, logging.ERROR, "event_handler_failed",
                            component="event_bus", operation="dispatch",
                            outcome="FAILURE", event_type=event.event_type,
                            handler=getattr(handler, "__name__", type(handler).__name__),
                            exception_type=type(exc).__name__,
                            recommendation="Inspect the handler traceback and affected component; event processing continues for other events.",
                        )
            finally:
                self._queue.task_done()
        self._running = False
        log_event(
            logger, logging.INFO, "event_bus_stopped",
            component="event_bus", operation="stop",
            outcome="SUCCESS", dropped_count=self._dropped,
        )

    async def stop(self) -> None:
        was_running = self._running
        self._stopping = True
        self._running = False
        if was_running:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("EventBus stop timed out with %d queued events", self._queue.qsize())

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def dropped(self) -> int:
        return self._dropped