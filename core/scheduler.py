"""Scheduler: manages periodic tasks."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self):
        self._tasks: list[asyncio.Task] = []
        self._running = False

    def schedule(self, interval: float, coro: Callable[[], Coroutine[Any, Any, None]]) -> None:
        async def _wrapper():
            while self._running:
                try:
                    await coro()
                except Exception as e:
                    logger.error("Scheduled task failed: %s", e)
                await asyncio.sleep(interval)
        self._tasks.append(asyncio.create_task(_wrapper()))

    async def start(self) -> None:
        self._running = True
        logger.info("Scheduler started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        logger.info("Scheduler stopped")
