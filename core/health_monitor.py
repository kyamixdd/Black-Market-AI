"""Health monitor: tracks system health metrics and alerts."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(self):
        self._started_monotonic = time.monotonic()
        self.metrics: dict[str, Any] = {
            "status": "UNKNOWN",
            "components": {},
            "last_check": None,
            "metrics": {},
        }

    def check_component(self, name: str, is_healthy: bool, details: str | None = None) -> None:
        previous = self.metrics["components"].get(name)
        component = {
            "healthy": is_healthy,
            "details": details,
        }
        self.metrics["components"][name] = component
        self._update_status()
        if not is_healthy:
            if previous != component:
                logger.warning("Component %s is unhealthy: %s", name, details)

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        self.metrics["metrics"].update(metrics)
        self._update_status()

    def _update_status(self) -> None:
        components = self.metrics["components"]
        if not components:
            self.metrics["status"] = "UNKNOWN"
        elif all(component["healthy"] for component in components.values()):
            self.metrics["status"] = "OK"
        else:
            self.metrics["status"] = "DEGRADED"
        self.metrics["last_check"] = datetime.now(timezone.utc).isoformat()

    def get_status(self) -> dict[str, Any]:
        return {
            **self.metrics,
            "components": {
                name: dict(component)
                for name, component in self.metrics["components"].items()
            },
            "metrics": {
                **self.metrics["metrics"],
                "uptime_seconds": max(0.0, time.monotonic() - self._started_monotonic),
            },
        }
