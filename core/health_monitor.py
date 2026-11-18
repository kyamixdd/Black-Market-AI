"""Health monitor: tracks backend component health and uptime."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(self):
        self._started_at = time.monotonic()
        self.metrics: dict[str, Any] = {
            "status": "OK",
            "components": {},
            "last_check": None,
            "metrics": {"uptime_seconds": 0.0},
        }

    def check_component(self, name: str, is_healthy: bool, details: str | None = None) -> None:
        self.metrics["components"][name] = {
            "healthy": bool(is_healthy),
            "details": details,
        }
        self.metrics["last_check"] = datetime.now(timezone.utc).isoformat()
        self.metrics["status"] = (
            "OK" if all(component["healthy"] for component in self.metrics["components"].values())
            else "DEGRADED"
        )
        if not is_healthy:
            logger.warning("Component %s is unhealthy: %s", name, details)

    def get_status(self) -> dict[str, Any]:
        self.metrics["metrics"]["uptime_seconds"] = max(0.0, time.monotonic() - self._started_at)
        return self.metrics
