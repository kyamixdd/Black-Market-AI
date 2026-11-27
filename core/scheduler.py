"""Scheduler: manages periodic tasks."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self):
        self._jobs: list[tuple[float, Callable[[], Coroutine[Any, Any, None]]]] = []
        self._tasks: list[asyncio.Task] = []
        self._running = False

    def _spawn_job(self, interval: float, coro: Callable[[], Coroutine[Any, Any, None]]) -> None:
        async def _wrapper():
            while self._running:
                try:
                    await coro()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("Scheduled task failed: %s", e)
                await asyncio.sleep(interval)

        self._tasks.append(asyncio.create_task(_wrapper()))

    def schedule(self, interval: float, coro: Callable[[], Coroutine[Any, Any, None]]) -> None:
        self._jobs.append((interval, coro))
        if self._running:
            self._spawn_job(interval, coro)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for interval, coro in self._jobs:
            self._spawn_job(interval, coro)
        logger.info("Scheduler started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
        logger.info("Scheduler stopped")
