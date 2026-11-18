"""Health monitor: tracks system health metrics and alerts."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

class HealthMonitor:
    def __init__(self):
        self.metrics: dict[str, Any] = {
            "status": "OK",
            "components": {},
            "last_check": None,
        }

    def check_component(self, name: str, is_healthy: bool, details: str | None = None) -> None:
        self.metrics["components"][name] = {
            "healthy": is_healthy,
            "details": details,
        }
        if not is_healthy:
            self.metrics["status"] = "DEGRADED"
            logger.warning("Component %s is unhealthy: %s", name, details)
        else:
            # Check if all components are now healthy
            if all(c["healthy"] for c in self.metrics["components"].values()):
                self.metrics["status"] = "OK"

    def get_status(self) -> dict[str, Any]:
        return self.metrics
