"""WebSocket manager for real-time updates to frontend."""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import WebSocket
from pydantic import BaseModel, ValidationError
from starlette.websockets import WebSocketDisconnect

from core.event_bus import EventBus
from core.event_models import Event, EventType
from ..routes.schemas import (
    SystemEventResponse,
    WebSocketAcknowledgement,
    WebSocketChannel,
    WebSocketClientMessage,
    WebSocketEventMessage,
)

logger = logging.getLogger(__name__)

EVENT_TO_CHANNELS: dict[EventType, tuple[WebSocketChannel, ...]] = {
    EventType.MARKET_DATA: (WebSocketChannel.PRICE_UPDATES,),
    EventType.MARKET_SNAPSHOT: (WebSocketChannel.MARKET_UPDATES,),
    EventType.SIGNAL_PROPOSED: (WebSocketChannel.SIGNAL_UPDATES,),
    EventType.SIGNAL_VALIDATED: (WebSocketChannel.SIGNAL_UPDATES,),
    EventType.SIGNAL_REJECTED: (
        WebSocketChannel.SIGNAL_UPDATES,
        WebSocketChannel.SYSTEM_EVENTS,
    ),
    EventType.SIGNAL_EXPIRED: (WebSocketChannel.SIGNAL_UPDATES,),
    EventType.PREDICTION: (WebSocketChannel.LEARNING_UPDATES,),
    EventType.TRADE_EXECUTED: (
        WebSocketChannel.PORTFOLIO_UPDATES,
        WebSocketChannel.POSITION_UPDATES,
    ),
    EventType.TRADE_PARTIALLY_FILLED: (
        WebSocketChannel.PORTFOLIO_UPDATES,
        WebSocketChannel.POSITION_UPDATES,
    ),
    EventType.TRADE_CLOSED: (
        WebSocketChannel.PORTFOLIO_UPDATES,
        WebSocketChannel.POSITION_UPDATES,
    ),
    EventType.TRADE_CANCELLED: (
        WebSocketChannel.PORTFOLIO_UPDATES,
        WebSocketChannel.SYSTEM_EVENTS,
    ),
    EventType.TRADE_REJECTED: (
        WebSocketChannel.PORTFOLIO_UPDATES,
        WebSocketChannel.SYSTEM_EVENTS,
    ),
    EventType.POSITION_OPENED: (
        WebSocketChannel.POSITION_UPDATES,
        WebSocketChannel.PORTFOLIO_UPDATES,
    ),
    EventType.POSITION_CLOSED: (
        WebSocketChannel.POSITION_UPDATES,
        WebSocketChannel.PORTFOLIO_UPDATES,
    ),
    EventType.ORDER_PLACED: (WebSocketChannel.PORTFOLIO_UPDATES,),
    EventType.ORDER_FILLED: (
        WebSocketChannel.PORTFOLIO_UPDATES,
        WebSocketChannel.POSITION_UPDATES,
    ),
    EventType.LEARNING_UPDATE: (WebSocketChannel.LEARNING_UPDATES,),
    EventType.MODEL_TRAINED: (WebSocketChannel.LEARNING_UPDATES,),
    EventType.MODEL_PROMOTED: (WebSocketChannel.LEARNING_UPDATES,),
    EventType.MODEL_ROLLED_BACK: (WebSocketChannel.LEARNING_UPDATES,),
    EventType.RISK_ALERT: (
        WebSocketChannel.RISK_UPDATES,
        WebSocketChannel.SYSTEM_EVENTS,
    ),
    EventType.SYSTEM_HEALTH: (WebSocketChannel.SYSTEM_EVENTS,),
    EventType.NOTIFICATION: (WebSocketChannel.SYSTEM_EVENTS,),
}


class WebSocketManager:
    """Manages WebSocket connections and event distribution to frontend."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[WebSocketChannel, set[str]] = {}
        self._connection_channels: dict[str, set[WebSocketChannel]] = {}
        self._running = False

    async def start(self) -> None:
        """Start the WebSocket manager and subscribe to EventBus."""
        if self._running:
            return
        self._running = True
        for event_type in EVENT_TO_CHANNELS:
            self.event_bus.subscribe(event_type, self._on_event)
        logger.info("WebSocket manager started")

    async def shutdown(self) -> None:
        """Shutdown the WebSocket manager."""
        self._running = False
        # Close all connections
        for ws in list(self._connections.values()):
            try:
                await ws.close()
            except Exception:
                logger.warning("Unable to close a WebSocket during shutdown", exc_info=True)
        self._connections.clear()
        self._subscriptions.clear()
        self._connection_channels.clear()
        self._running = False

    def connect(self, websocket: WebSocket) -> str:
        """Register a new WebSocket connection."""
        connection_id = uuid.uuid4().hex[:12]
        self._connections[connection_id] = websocket
        self._connection_channels[connection_id] = set()
        logger.info(f"WebSocket connected: {connection_id} (total: {len(self._connections)})")
        return connection_id

    def disconnect(self, websocket: WebSocket) -> None:
        """Disconnect a WebSocket."""
        connection_id = None
        for cid, ws in self._connections.items():
            if ws == websocket:
                connection_id = cid
                break

        if connection_id:
            # Remove from all subscriptions
            for channel, subs in self._subscriptions.items():
                subs.discard(connection_id)
            self._connections.pop(connection_id, None)
            self._connection_channels.pop(connection_id, None)
            logger.info(f"WebSocket disconnected: {connection_id} (remaining: {len(self._connections)})")

    async def handle_message(self, websocket: WebSocket, message: str) -> None:
        """Handle incoming WebSocket message from frontend."""
        try:
            request = WebSocketClientMessage.model_validate_json(message)
        except ValidationError:
            logger.warning("Rejected invalid WebSocket request")
            await self._send(
                websocket,
                WebSocketAcknowledgement(
                    type="error",
                    detail="Expected subscribe, unsubscribe, or ping with supported channels",
                ),
            )
            return

        if request.type == "subscribe":
            await self._handle_subscribe(websocket, request.channels)
        elif request.type == "unsubscribe":
            await self._handle_unsubscribe(websocket, request.channels)
        else:
            await self._send(websocket, WebSocketAcknowledgement(type="pong"))

    async def _handle_subscribe(
        self,
        websocket: WebSocket,
        channels: list[WebSocketChannel],
    ) -> None:
        """Handle subscription request."""
        connection_id = self._get_connection_id(websocket)

        if not connection_id:
            return

        for channel in channels:
            self._subscriptions.setdefault(channel, set()).add(connection_id)
            self._connection_channels[connection_id].add(channel)

        await self._send(
            websocket,
            WebSocketAcknowledgement(
                type="subscribed",
                channels=sorted(
                    self._connection_channels.get(connection_id, set()),
                    key=lambda item: item.value,
                ),
            ),
        )
        logger.debug("Connection %s subscribed to: %s", connection_id, channels)

    async def _handle_unsubscribe(
        self,
        websocket: WebSocket,
        channels: list[WebSocketChannel],
    ) -> None:
        """Handle unsubscription request."""
        connection_id = self._get_connection_id(websocket)

        if not connection_id:
            return

        for channel in channels:
            self._subscriptions.get(channel, set()).discard(connection_id)
            self._connection_channels.get(connection_id, set()).discard(channel)

        await self._send(
            websocket,
            WebSocketAcknowledgement(type="unsubscribed", channels=channels),
        )
        logger.debug("Connection %s unsubscribed from: %s", connection_id, channels)

    def _get_connection_id(self, websocket: WebSocket) -> str | None:
        """Get connection ID for a websocket."""
        for cid, ws in self._connections.items():
            if ws == websocket:
                return cid
        return None

    async def _on_event(self, event: Event) -> None:
        """Handle event from EventBus and forward to subscribed WebSocket connections."""
        channels = EVENT_TO_CHANNELS.get(event.event_type, ())
        if not channels:
            return

        event_data = SystemEventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            source=event.source,
            symbol=event.symbol,
            market=event.market,
            payload=event.payload,
        )
        for channel in channels:
            for connection_id in list(self._subscriptions.get(channel, set())):
                websocket = self._connections.get(connection_id)
                if websocket:
                    await self._send(
                        websocket,
                        WebSocketEventMessage(channel=channel, event=event_data),
                    )

    async def _send(self, websocket: WebSocket, message: BaseModel) -> None:
        """Send JSON message to WebSocket."""
        try:
            await websocket.send_text(message.model_dump_json())
        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected before message delivery")
            self.disconnect(websocket)
        except Exception:
            logger.warning("Unable to send a WebSocket message; dropping connection", exc_info=True)
            self.disconnect(websocket)

    def get_stats(self) -> dict:
        """Get WebSocket manager statistics."""
        return {
            "total_connections": len(self._connections),
            "channels": {ch.value: len(subs) for ch, subs in self._subscriptions.items()},
            "running": self._running,
        }


class WebSocketConnection:
    """Wrapper for WebSocket connection with metadata."""

    def __init__(self, websocket, connection_id: str):
        self.websocket = websocket
        self.connection_id = connection_id
        self.connected_at = None
        self.subscribed_channels: set[str] = set()