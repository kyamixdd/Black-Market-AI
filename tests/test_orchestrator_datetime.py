"""Regression tests for timezone-aware datetime use in the orchestrator."""
from datetime import datetime, timezone
from types import SimpleNamespace

from core.orchestrator import Orchestrator


class _TickerCache:
    def __init__(self, timestamp):
        self.timestamp = timestamp

    def get_market_tickers(self, market):
        return [{"timestamp": self.timestamp}]


def _orchestrator_with_fresh_ticker():
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.cache = _TickerCache(datetime.now(timezone.utc))
    return orchestrator


def test_has_fresh_market_data_executes_with_timezone_aware_timestamp():
    orchestrator = _orchestrator_with_fresh_ticker()

    assert orchestrator.has_fresh_market_data() is True


def test_update_health_executes_market_data_timestamp_logic():
    orchestrator = _orchestrator_with_fresh_ticker()
    orchestrator.db = SimpleNamespace(health=lambda: {"status": "ok"})
    orchestrator.health_monitor = SimpleNamespace(check_component=lambda *args: None)
    orchestrator._event_bus_task = None
    orchestrator.event_bus = SimpleNamespace(dropped=0)
    orchestrator.scanner = SimpleNamespace(_running=True)
    orchestrator._tasks = []

    orchestrator._update_health()
