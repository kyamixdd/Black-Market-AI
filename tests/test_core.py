"""Test health monitor and scheduler."""
import asyncio

import pytest

from core.health_monitor import HealthMonitor
from core.scheduler import Scheduler


def test_health_monitor():
    hm = HealthMonitor()
    assert hm.get_status()["status"] == "UNKNOWN"
    assert hm.get_status()["metrics"]["uptime_seconds"] >= 0

    hm.check_component("DB", False, "Connection failed")
    assert hm.get_status()["status"] == "DEGRADED"
    assert hm.get_status()["components"]["DB"]["healthy"] is False

    hm.check_component("DB", True)
    assert hm.get_status()["status"] == "OK"


def test_orchestrator_health_snapshot_exposes_runtime_readiness():
    from types import SimpleNamespace

    from core.orchestrator import Orchestrator

    scanner_status = {
        "running": True,
        "configured_timeframes": ["1m", "1h"],
        "markets": {
            "SPOT": {"state": "COMPLETE", "refresh_failures": 0, "last_error": None},
            "FUTURES": {"state": "COMPLETE", "refresh_failures": 0, "last_error": None},
        },
    }
    runtime = SimpleNamespace(
        health_monitor=HealthMonitor(),
        db=object(),
        scanner=SimpleNamespace(
            enabled_markets={"SPOT", "FUTURES"},
            status_snapshot=lambda: scanner_status,
        ),
        ws_manager=SimpleNamespace(status_snapshot=lambda: {"state": "LIVE"}),
        intelligence=SimpleNamespace(predictor=SimpleNamespace(is_trained=False)),
        learning_service=SimpleNamespace(
            state="validation_failed",
            last_training_result={"reason": "holdout_threshold_not_met"},
            last_cycle_status="validation_failed",
        ),
        simulator=object(),
        registry=SimpleNamespace(count=lambda market: 10),
        _autonomous_enabled=True,
    )

    health = Orchestrator.refresh_health_status(runtime)

    assert health["status"] == "DEGRADED"
    assert health["components"]["market_scanner"]["healthy"] is True
    assert health["components"]["exchange_websocket"]["healthy"] is True
    assert health["components"]["learning_model"]["healthy"] is False
    assert "holdout_threshold_not_met" in health["components"]["learning_model"]["details"]
    assert health["metrics"]["eligible_symbols"] == {"SPOT": 10, "FUTURES": 10}


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
