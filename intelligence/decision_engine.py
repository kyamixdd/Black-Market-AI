"""Decision engine: validates signals, evaluates risk, and manages confidence."""
from __future__ import annotations

import logging
from typing import Any

from core.event_bus import EventBus
from core.event_models import EventType, make_event
from intelligence.confidence_engine import ConfidenceEngine
from intelligence.signal_validator import SignalValidator

logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.validator = SignalValidator()
        self.confidence_engine = ConfidenceEngine()

    async def evaluate_signal(self, signal: dict[str, Any]) -> None:
        """Validate a proposed signal and publish a terminal decision event."""
        signal = dict(signal)
        signal_id = signal.get("signal_id", "unknown")

        is_valid, reason = self.validator.validate(signal)
        if not is_valid:
            signal["reject_reason"] = reason
            await self.event_bus.publish(make_event(
                EventType.SIGNAL_REJECTED,
                "decision_engine",
                **signal,
            ))
            logger.info("Signal %s rejected: %s", signal_id, reason)
            return

        confidence = self.confidence_engine.calculate(signal)
        signal["confidence"] = confidence
        if confidence >= 0.65:
            await self.event_bus.publish(make_event(
                EventType.SIGNAL_VALIDATED,
                "decision_engine",
                **signal,
            ))
            logger.info("Signal %s validated (confidence %.2f)", signal_id, confidence)
            return

        signal["reject_reason"] = "Low confidence"
        await self.event_bus.publish(make_event(
            EventType.SIGNAL_REJECTED,
            "decision_engine",
            **signal,
        ))
        logger.info("Signal %s rejected: low confidence %.2f", signal_id, confidence)
