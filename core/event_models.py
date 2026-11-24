"""Structured event definitions for the BlackMarket Intelligence Bus."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    SIGNAL_PROPOSED = "SIGNAL_PROPOSED"
    SIGNAL_VALIDATED = "SIGNAL_VALIDATED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    PREDICTION = "PREDICTION"
    TRADE_PROPOSED = "TRADE_PROPOSED"
    TRADE_EXECUTED = "TRADE_EXECUTED"
    TRADE_PARTIALLY_FILLED = "TRADE_PARTIALLY_FILLED"
    TRADE_CLOSED = "TRADE_CLOSED"
    TRADE_CANCELLED = "TRADE_CANCELLED"
    TRADE_REJECTED = "TRADE_REJECTED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_FILLED = "ORDER_FILLED"
    LEARNING_UPDATE = "LEARNING_UPDATE"
    MODEL_TRAINED = "MODEL_TRAINED"
    MODEL_PROMOTED = "MODEL_PROMOTED"
    MODEL_ROLLED_BACK = "MODEL_ROLLED_BACK"
    RISK_ALERT = "RISK_ALERT"
    SYSTEM_HEALTH = "SYSTEM_HEALTH"
    NOTIFICATION = "NOTIFICATION"


class Event(BaseModel):
    """Every internal message follows this structure."""
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    symbol: str | None = None
    market: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def make_event(event_type: str, source: str, symbol: str | None = None,
               market: str | None = None, **payload: Any) -> Event:
    return Event(event_type=event_type, source=source, symbol=symbol,
                 market=market, payload=payload)