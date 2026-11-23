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
        """Validate a proposed signal and publish if high quality."""
        # Check basic rules
        is_valid, reason = self.validator.validate(signal)
        if not is_valid:
            logger.debug("Signal %s rejected: %s", signal["signal_id"], reason)
            return
        # Evaluate confidence
        confidence = self.confidence_engine.calculate(signal)
        signal["confidence"] = confidence
        # Event envelope fields belong on Event, not duplicated in its payload.
        event_payload = {
            key: value for key, value in signal.items()
            if key not in {"symbol", "market"}
        }
        # High confidence threshold
        if confidence >= 0.65:
            await self.event_bus.publish(make_event(
                EventType.SIGNAL_VALIDATED, "decision_engine",
                symbol=signal["symbol"], market=signal["market"],
                **event_payload
            ))
            logger.info("Signal %s validated (conf: %.2f)", signal["signal_id"], confidence)
        else:
            await self.event_bus.publish(make_event(
                EventType.SIGNAL_REJECTED, "decision_engine",
                symbol=signal["symbol"], market=signal["market"],
                reason="Low confidence", **event_payload
            ))