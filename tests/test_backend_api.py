import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from core.event_bus import EventBus
from core.event_models import EventType, make_event
from src_tauri.backend.api.routes.schemas import WebSocketChannel
from src_tauri.backend.api.websocket.manager import WebSocketManager


class LoopbackTestClient:
    """Give in-process API clients the same peer address as the desktop app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            scope = dict(scope)
            scope["client"] = ("127.0.0.1", 50000)
        await self.app(scope, receive, send)


class FakeWebSocket:
    def __init__(self):
        self.messages: list[str] = []
        self.closed = False

    async def send_text(self, message: str) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_websocket_routes_event_bus_updates_to_typed_channels():
    event_bus = EventBus()
    manager = WebSocketManager(event_bus)
    websocket = FakeWebSocket()
    await manager.start()
    manager.connect(websocket)

    await manager.handle_message(
        websocket,
        json.dumps({
            "type": "subscribe",
            "channels": [channel.value for channel in WebSocketChannel],
        }),
    )
    acknowledgement = json.loads(websocket.messages[0])
    assert acknowledgement["type"] == "subscribed"
    assert set(acknowledgement["channels"]) == {
        channel.value for channel in WebSocketChannel
    }

    consumer = asyncio.create_task(event_bus.run())
    await event_bus.publish(
        make_event(EventType.MARKET_DATA, "scanner", symbol="BTCUSDT", price=100_000)
    )
    await event_bus.publish(
        make_event(
            EventType.POSITION_OPENED,
            "simulator",
            symbol="BTCUSDT",
            market="SPOT",
        )
    )

    async def wait_for_all_updates():
        while len(websocket.messages) < 4:
            await asyncio.sleep(0)

    try:
        await asyncio.wait_for(wait_for_all_updates(), timeout=1)
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)

    updates = [json.loads(message) for message in websocket.messages[1:]]
    assert {update["channel"] for update in updates} == {
        "price_updates",
        "position_updates",
        "portfolio_updates",
    }
    assert all(update["type"] == "event" for update in updates)


@pytest.mark.asyncio
async def test_websocket_rejects_unknown_channels_without_subscribing():
    manager = WebSocketManager(EventBus())
    websocket = FakeWebSocket()
    manager.connect(websocket)

    await manager.handle_message(
        websocket,
        json.dumps({"type": "subscribe", "channels": ["unknown"]}),
    )

    response = json.loads(websocket.messages[0])
    assert response["type"] == "error"
    assert manager.get_stats()["channels"] == {}


def test_read_api_root_endpoints_use_typed_responses(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src_tauri.backend.api.routes import intelligence, learning, portfolio

    class FakeBridge:
        @staticmethod
        def get_portfolio_summary():
            return {
                "spot_balance": 500.0,
                "futures_balance": 500.0,
                "total_balance": 1000.0,
                "spot_pnl": 0.0,
                "futures_pnl": 0.0,
                "total_pnl": 0.0,
                "spot_return_pct": 0.0,
                "futures_return_pct": 0.0,
                "total_return_pct": 0.0,
            }

        @staticmethod
        def get_learning_status():
            return {
                "model_status": "Not Trained",
                "rf_loaded": False,
                "xgb_loaded": False,
                "river_available": False,
                "version": None,
                "predictions_total": 0,
                "predictions_resolved": 0,
                "accuracy": 0.0,
                "recent_predictions": [],
            }

        @staticmethod
        def get_strategy_metrics():
            return []

        @staticmethod
        def get_strategy_weights():
            return {}

    bridge = FakeBridge()
    monkeypatch.setattr(portfolio, "get_bridge", lambda: bridge)
    monkeypatch.setattr(learning, "get_bridge", lambda: bridge)
    monkeypatch.setattr(intelligence, "get_bridge", lambda: bridge)

    app = FastAPI()
    for router in (portfolio.router, intelligence.router, learning.router):
        app.include_router(router, prefix="/api")

    with TestClient(app) as client:
        portfolio_response = client.get("/api/portfolio")
        assert portfolio_response.status_code == 200
        assert portfolio_response.json()["total_balance"] == 1000.0
        assert client.get("/api/portfolio/summary").json() == portfolio_response.json()

        learning_response = client.get("/api/learning")
        assert learning_response.status_code == 200
        assert learning_response.json()["model_status"] == "Not Trained"
        assert client.get("/api/learning/status").json() == learning_response.json()

        intelligence_response = client.get("/api/intelligence")
        assert intelligence_response.status_code == 200
        assert intelligence_response.json() == {
            "strategies": [],
            "strategy_weights": {},
        }


def test_market_analytics_reads_persisted_snapshots_when_cache_is_empty(tmp_path):
    from database.connection import Database
    from database.repositories import Repository
    from src_tauri.backend.bridge.orchestrator_bridge import OrchestratorBridge

    db = Database(f"sqlite:///{tmp_path / 'market-analytics.db'}")
    db.init_db()
    repo = Repository(db.session_maker())
    repo.save_snapshot({
        "symbol": "BTCUSDT",
        "market": "SPOT",
        "price": 101.0,
        "volume_24h": 1_000.0,
        "price_change_24h": 1.0,
    })
    orchestrator = SimpleNamespace(
        repo=repo,
        cache=SimpleNamespace(get_market_tickers=lambda _market: []),
        event_bus=object(),
        candle_manager=object(),
        simulator=SimpleNamespace(risk_manager=object()),
        intelligence=object(),
    )
    bridge = OrchestratorBridge(orchestrator)

    heatmap = bridge.get_market_heatmap()
    breadth = bridge.get_market_breadth()

    assert [item["symbol"] for item in heatmap] == ["BTCUSDT"]
    assert breadth["advancing"] == 1
    assert breadth["declining"] == 0
    assert breadth["total_volume"] == 1_000.0
    db.close()


def test_main_api_registers_requested_read_routes():
    from src_tauri.backend.main import app

    paths = {route.path for route in app.routes}
    assert {
        "/api/system/status",
        "/api/markets",
        "/api/markets/{symbol}",
        "/api/markets/{symbol}/candles",
        "/api/signals",
        "/api/portfolio",
        "/api/positions",
        "/api/trades",
        "/api/trades/orders",
        "/api/positions/{position_id}/close",
        "/api/intelligence",
        "/api/learning",
        "/api/risk/status",
        "/api/activity",
        "/ws",
    }.issubset(paths)

    status_schema = app.openapi()["paths"]["/api/system/status"]["get"]["responses"]["200"]
    assert status_schema["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SystemHealthResponse"
    )


def test_backend_startup_stops_when_database_integrity_check_fails(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI

    from src_tauri.backend import main

    class CorruptDatabase:
        def __init__(self, _url):
            pass

        @staticmethod
        def init_db():
            pass

        @staticmethod
        def integrity_check():
            return "database disk image is malformed"

    monkeypatch.setattr(main, "validate_config_or_exit", lambda: None)
    monkeypatch.setattr(main, "Database", CorruptDatabase)
    with pytest.raises(RuntimeError, match="integrity check failed"):
        asyncio.run(main.lifespan(FastAPI()).__aenter__())


def test_system_status_returns_the_health_monitor_snapshot(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src_tauri.backend import main
    from src_tauri.backend.api.routes.schemas import SystemHealthResponse

    class FakeHealthMonitor:
        @staticmethod
        def get_status():
            return {
                "status": "OK",
                "components": {"database": {"healthy": True}},
                "metrics": {"uptime_seconds": 12.5},
            }

    class FakeOrchestrator:
        health_monitor = FakeHealthMonitor()

    monkeypatch.setattr(main, "orchestrator", FakeOrchestrator())
    app = FastAPI()
    app.add_api_route(
        "/api/system/status",
        main.system_status,
        response_model=SystemHealthResponse,
    )

    with TestClient(app) as client:
        response = client.get("/api/system/status")
        assert response.status_code == 200
        assert response.json() == {
            "status": "OK",
            "components": {"database": {"healthy": True}},
            "metrics": {"uptime_seconds": 12.5},
            "uptime_seconds": 12.5,
        }


def test_internal_shutdown_requires_the_supervisor_token(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src_tauri.backend import main

    app = FastAPI()
    app.add_api_route(
        "/_internal/shutdown",
        main.shutdown_backend,
        methods=["POST"],
    )
    shutdown_calls = []
    monkeypatch.setattr(main, "_shutdown_token", None)
    monkeypatch.setattr(
        main,
        "_request_server_shutdown",
        lambda: shutdown_calls.append(True),
    )

    with TestClient(app) as client:
        assert client.post("/_internal/shutdown").status_code == 404

        monkeypatch.setattr(main, "_shutdown_token", "private-test-token")
        assert client.post(
            "/_internal/shutdown",
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code == 403

        monkeypatch.setattr(main, "_request_server_shutdown", None)
        assert client.post(
            "/_internal/shutdown",
            headers={"Authorization": "Bearer private-test-token"},
        ).status_code == 503

        monkeypatch.setattr(
            main,
            "_request_server_shutdown",
            lambda: shutdown_calls.append(True),
        )
        response = client.post(
            "/_internal/shutdown",
            headers={"Authorization": "Bearer private-test-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}
    assert shutdown_calls == [True]


def test_websocket_endpoint_accepts_and_handles_messages(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src_tauri.backend import main

    manager = WebSocketManager(EventBus())
    monkeypatch.setattr(main, "ws_manager", manager)
    monkeypatch.setattr(main, "_api_token", "private-api-token")
    app = FastAPI()
    app.websocket("/ws")(main.websocket_endpoint)

    with TestClient(LoopbackTestClient(app)) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "authenticate", "token": "private-api-token"})
            assert websocket.receive_json()["type"] == "authenticated"
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json()["type"] == "pong"


def test_websocket_rejects_unauthenticated_client_before_registering(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from starlette.websockets import WebSocketDisconnect
    from fastapi.testclient import TestClient

    from src_tauri.backend import main

    manager = WebSocketManager(EventBus())
    monkeypatch.setattr(main, "ws_manager", manager)
    monkeypatch.setattr(main, "_api_token", "private-api-token")
    app = FastAPI()
    app.websocket("/ws")(main.websocket_endpoint)

    with TestClient(LoopbackTestClient(app)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "subscribe", "channels": ["portfolio_updates"]})
                websocket.receive_json()
    assert manager.get_stats()["total_connections"] == 0


def test_websocket_endpoint_handles_disconnect_after_failed_send(monkeypatch):
    from starlette.websockets import WebSocketState

    from src_tauri.backend import main

    disconnects = []

    class DisconnectingWebSocket:
        client = SimpleNamespace(host="127.0.0.1")
        application_state = WebSocketState.CONNECTING
        authenticated = False

        async def accept(self):
            self.application_state = WebSocketState.CONNECTED

        async def receive_text(self):
            if not self.authenticated:
                self.authenticated = True
                return json.dumps({"type": "authenticate", "token": "private-api-token"})
            raise RuntimeError("WebSocket is not connected")

        async def send_json(self, _message):
            self.application_state = WebSocketState.DISCONNECTED

    manager = SimpleNamespace(
        connect=lambda _websocket: None,
        disconnect=lambda websocket: disconnects.append(websocket),
    )
    monkeypatch.setattr(main, "ws_manager", manager)
    monkeypatch.setattr(main, "_api_token", "private-api-token")

    asyncio.run(main.websocket_endpoint(DisconnectingWebSocket()))

    assert len(disconnects) == 1


def test_rest_api_requires_bearer_token_and_restricts_cors(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from src_tauri.backend import main

    monkeypatch.setattr(main, "_api_token", "private-api-token")
    client = TestClient(LoopbackTestClient(main.app))
    try:
        assert client.get("/api/system/status").status_code == 401
        assert client.get(
            "/api/system/status",
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code == 401

        authorized = client.get(
            "/api/system/status",
            headers={
                "Authorization": "Bearer private-api-token",
                "Origin": "http://tauri.localhost",
            },
        )
        assert authorized.status_code == 503
        assert authorized.headers["access-control-allow-origin"] == "http://tauri.localhost"
        assert "access-control-allow-credentials" not in authorized.headers

        untrusted = client.get(
            "/api/system/status",
            headers={
                "Authorization": "Bearer private-api-token",
                "Origin": "https://untrusted.example",
            },
        )
        assert "access-control-allow-origin" not in untrusted.headers
    finally:
        client.close()


@pytest.mark.asyncio
async def test_historical_candles_are_bounded_closed_sorted_and_deduplicated():
    from src_tauri.backend.bridge.orchestrator_bridge import OrchestratorBridge

    now_ms = int(time.time() * 1000)
    end_time = now_ms + 10_000

    class FakeClient:
        def __init__(self):
            self.request = None

        async def get_klines(self, symbol, interval, start_ms=None, end_ms=None, limit=500):
            self.request = (symbol, interval, end_ms, limit)
            return [
                [3000, "100", "103", "99", "102", "10", 3999],
                [1000, "100", "101", "99", "100.5", "8", 1999],
                [1000, "100", "102", "99", "101", "9", 1999],
                [now_ms + 1000, "100", "101", "99", "100", "1", now_ms + 1999],
                [now_ms + 5000, "100", "101", "99", "100", "1", now_ms + 15000],
            ]

    spot_client = FakeClient()
    bridge = object.__new__(OrchestratorBridge)
    bridge.orch = SimpleNamespace(spot_client=spot_client, futures_client=FakeClient())

    candles = await bridge.get_candles(
        "BTCUSDT",
        "SPOT",
        "1m",
        limit=500,
        end_time=end_time,
    )

    assert spot_client.request == ("BTCUSDT", "1m", end_time, 500)
    assert [candle["open_time"] for candle in candles] == [1000, 3000]
    assert candles[0]["close"] == 101



def test_tauri_webview_preflight_allows_authenticated_patch_and_delete(monkeypatch):
    from fastapi.testclient import TestClient
    from src_tauri.backend import main

    monkeypatch.setattr(main, "_api_token", "desktop-test-token")
    client = TestClient(LoopbackTestClient(main.app))
    origin = "http://tauri.localhost"
    try:
        for method in ("PATCH", "DELETE"):
            response = client.options(
                "/api/positions/test-position",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert method in response.headers["access-control-allow-methods"]
            assert "authorization" in response.headers["access-control-allow-headers"].lower()
    finally:
        client.close()


def test_tauri_origin_can_update_position_risk_over_authenticated_patch(monkeypatch):
    from fastapi.testclient import TestClient
    from src_tauri.backend import main
    from src_tauri.backend.api.routes import positions

    position = {
        "position_id": "paper-1", "symbol": "BTCUSDT", "market": "SPOT",
        "side": "LONG", "entry_price": 100.0, "current_price": 100.0,
        "amount": 1.0, "status": "OPEN", "stop_loss": 95.0,
        "take_profit": 110.0,
    }
    persisted = []
    simulator = SimpleNamespace(
        spot_positions={"paper-1": position}, futures_positions={},
        persist_position_callback=lambda value: persisted.append(dict(value)),
    )
    monkeypatch.setattr(positions, "get_bridge", lambda: SimpleNamespace(simulator=simulator))
    monkeypatch.setattr(main, "_api_token", "desktop-test-token")
    client = TestClient(LoopbackTestClient(main.app))
    origin = "http://tauri.localhost"
    try:
        preflight = client.options(
            "/api/positions/paper-1",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert preflight.status_code == 200
        response = client.patch(
            "/api/positions/paper-1",
            json={"stop_loss": 97.0, "take_profit": 108.0},
            headers={"Origin": origin, "Authorization": "Bearer desktop-test-token"},
        )
    finally:
        client.close()
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert position["stop_loss"] == 97.0
    assert position["take_profit"] == 108.0
    assert persisted[-1]["stop_loss"] == 97.0
    assert response.headers["access-control-allow-origin"] == origin

def test_partial_close_route_validates_and_dispatches_to_simulator(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src_tauri.backend.api.routes import positions

    calls = []
    position = {"position_id": "paper-2", "symbol": "BTCUSDT", "market": "SPOT", "status": "OPEN", "amount": 2.0}
    simulator = SimpleNamespace(
        spot_positions={"paper-2": position}, futures_positions={},
        _partial_close_position=lambda pos, price, quantity: calls.append((pos, price, quantity)) or True,
    )
    bridge = SimpleNamespace(
        simulator=simulator,
        get_market_snapshot=lambda *_: {"price": 101.0, "data_age_seconds": 1, "data_freshness": "LIVE"},
    )
    monkeypatch.setattr(positions, "get_bridge", lambda: bridge)
    app = FastAPI()
    app.include_router(positions.router, prefix="/api")
    with TestClient(app) as client:
        response = client.post("/api/positions/paper-2/partial-close", json={"quantity": 0.5})
        too_large = client.post("/api/positions/paper-2/partial-close", json={"quantity": 2.0})
    assert response.status_code == 200
    assert calls == [(position, 101.0, 0.5)]
    assert too_large.status_code == 422


def test_limit_order_cancel_route_dispatches_and_handles_non_open_orders(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src_tauri.backend.api.routes import trades

    calls = []
    open_order = {"order_id": "limit-1", "status": "OPEN"}
    simulator = SimpleNamespace(
        open_orders={"limit-1": open_order},
        cancel_limit_order=lambda order_id: calls.append(order_id) or {"status": "CANCELLED"},
    )
    monkeypatch.setattr(trades, "get_bridge", lambda: SimpleNamespace(simulator=simulator))
    app = FastAPI()
    app.include_router(trades.router, prefix="/api")
    with TestClient(app) as client:
        response = client.delete("/api/trades/orders/limit-1")
        open_order["status"] = "FILLING"
        filling = client.delete("/api/trades/orders/limit-1")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls == ["limit-1"]
    assert filling.status_code == 409
