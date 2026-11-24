"""Test health monitor and scheduler."""
import asyncio

import pytest

from core.health_monitor import HealthMonitor
from core.scheduler import Scheduler


def test_health_monitor():
    hm = HealthMonitor()
    assert hm.get_status()["status"] == "OK"

    hm.check_component("DB", False, "Connection failed")
    assert hm.get_status()["status"] == "DEGRADED"
    assert hm.get_status()["components"]["DB"]["healthy"] is False

    hm.check_component("DB", True)
    assert hm.get_status()["status"] == "OK"

@pytest.mark.asyncio
async def test_scheduler():
    sc = Scheduler()
    count = 0

    async def task():
        nonlocal count
        count += 1

    sc.schedule(0.1, task)
    await sc.start()

    await asyncio.sleep(0.25)
    await sc.stop()

    assert count >= 2
