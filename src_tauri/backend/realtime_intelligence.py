"""Bounded event-driven market intelligence and monitoring lifecycle.

Consumes the existing application EventBus; it does not open another market-data
connection or perform trading actions. Monitoring records are process-local.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from core.event_models import Event, EventType

logger = logging.getLogger(__name__)

MARKET_EVENTS = {EventType.MARKET_DATA.value, EventType.MARKET_SNAPSHOT.value}
VALID_CONDITIONS = {"price_above", "price_below"}


@dataclass
class MonitoringTask:
    task_id: str
    owner: str
    symbol: str
    market: str
    condition: str
    threshold: float
    created_at: datetime
    expires_at: datetime
    status: str = "active"
    triggered_at: datetime | None = None
    last_event_at: datetime | None = None
    trigger_count: int = 0
    last_trigger_price: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "symbol": self.symbol, "market": self.market,
            "condition": self.condition, "threshold": self.threshold,
            "created_at": self.created_at.isoformat(), "expires_at": self.expires_at.isoformat(),
            "status": self.status, "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "trigger_count": self.trigger_count, "last_trigger_price": self.last_trigger_price,
        }


class RealtimeIntelligence:
    """Processes existing market events with bounded buffering and task lifecycle."""

    def __init__(self, event_bus, *, queue_capacity: int = 256, max_tasks: int = 500,
                 event_id_capacity: int = 2048) -> None:
        self.event_bus = event_bus
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max(1, queue_capacity))
        self.max_tasks = max(1, max_tasks)
        self._tasks: dict[str, MonitoringTask] = {}
        self._owners: dict[str, str] = {}
        self._worker: asyncio.Task | None = None
        self._running = False
        self._dropped_events = 0
        self._processed_events = 0
        self._duplicate_events = 0
        self._event_ids: OrderedDict[str, None] = OrderedDict()
        self._event_id_capacity = max(1, event_id_capacity)
        self._last_event_at: datetime | None = None
        self._last_error: str | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.event_bus.subscribe_all(self.on_event)
        self._worker = asyncio.create_task(self._run(), name="blackmarket-realtime-intelligence")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        unsubscribe = getattr(self.event_bus, "unsubscribe_all", None)
        if callable(unsubscribe):
            unsubscribe(self.on_event)

    async def on_event(self, event: Event) -> None:
        if event.event_type not in MARKET_EVENTS:
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Market updates are state-like: discard the oldest queued update and
            # retain the newest so consumers recover toward current market state.
            self._dropped_events += 1
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                self.queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                logger.warning("Realtime intelligence queue saturated; event dropped")

    async def _run(self) -> None:
        while True:
            event = await self.queue.get()
            try:
                await self.process_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = type(exc).__name__
                logger.exception("Realtime market event processing failed")
            finally:
                self.queue.task_done()

    async def process_event(self, event: Event) -> None:
        if event.event_id in self._event_ids:
            self._duplicate_events += 1
            return
        self._event_ids[event.event_id] = None
        while len(self._event_ids) > self._event_id_capacity:
            self._event_ids.popitem(last=False)

        self._processed_events += 1
        self._last_event_at = event.timestamp
        now = datetime.now(timezone.utc)
        payload = event.payload if isinstance(event.payload, dict) else {}
        raw_price = payload.get("price", payload.get("last_price", payload.get("lastPrice")))
        try:
            price = float(raw_price)
        except (TypeError, ValueError, OverflowError):
            price = None
        if price is not None and (price <= 0 or not __import__("math").isfinite(price)):
            price = None

        for task in list(self._tasks.values()):
            if task.status != "active":
                continue
            if task.expires_at <= now:
                task.status = "expired"
                continue
            if task.symbol != (event.symbol or "").upper() or task.market != (event.market or "").upper():
                continue
            task.last_event_at = event.timestamp
            if price is None:
                continue
            matched = price > task.threshold if task.condition == "price_above" else price < task.threshold
            if matched:
                task.status = "triggered"
                task.triggered_at = now
                task.trigger_count += 1
                task.last_trigger_price = price

    def create_task(self, owner: str, symbol: str, market: str, condition: str,
                    threshold: float, *, ttl_seconds: int = 86400) -> dict[str, Any]:
        if not owner or len(owner) > 256:
            raise ValueError("Invalid monitoring owner.")
        symbol = symbol.strip().upper()
        market = market.strip().upper()
        if not symbol or len(symbol) > 32 or not symbol.isalnum():
            raise ValueError("Invalid market symbol.")
        if market not in {"SPOT", "FUTURES"}:
            raise ValueError("Unsupported market.")
        if condition not in VALID_CONDITIONS:
            raise ValueError("Unsupported monitoring condition.")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ValueError("Threshold must be numeric.")
        import math
        threshold = float(threshold)
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError("Threshold must be finite and positive.")
        if not 60 <= int(ttl_seconds) <= 30 * 86400:
            raise ValueError("Monitoring expiry must be between 60 seconds and 30 days.")
        self._expire_tasks()
        # Reclaim terminal records first; retain active tasks and cap history.
        for old_id, old_task in list(self._tasks.items()):
            if len(self._tasks) < self.max_tasks:
                break
            if old_task.status != "active":
                self._tasks.pop(old_id, None)
                self._owners.pop(old_id, None)
        if len(self._tasks) >= self.max_tasks:
            raise RuntimeError("Monitoring task capacity reached.")
        now = datetime.now(timezone.utc)
        task = MonitoringTask(
            task_id=uuid4().hex, owner=owner, symbol=symbol, market=market,
            condition=condition, threshold=threshold, created_at=now,
            expires_at=now + timedelta(seconds=int(ttl_seconds)),
        )
        self._tasks[task.task_id] = task
        self._owners[task.task_id] = owner
        return task.snapshot()

    def list_tasks(self, owner: str) -> list[dict[str, Any]]:
        self._expire_tasks()
        return [task.snapshot() for task in self._tasks.values() if task.owner == owner]

    def cancel_task(self, owner: str, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None or task.owner != owner:
            return False
        if task.status in {"active"}:
            task.status = "cancelled"
        return True

    def _expire_tasks(self) -> None:
        now = datetime.now(timezone.utc)
        for task in self._tasks.values():
            if task.status == "active" and task.expires_at <= now:
                task.status = "expired"

    def status_snapshot(self) -> dict[str, Any]:
        self._expire_tasks()
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            counts[task.status] = counts.get(task.status, 0) + 1
        return {
            "running": self._running, "queue_depth": self.queue.qsize(),
            "queue_capacity": self.queue.maxsize, "dropped_events": self._dropped_events,
            "processed_events": self._processed_events, "duplicate_events": self._duplicate_events,
            "monitoring_task_counts": counts,
            "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
            "last_error": self._last_error,
        }
