from __future__ import annotations

import asyncio
import hashlib
import json
from collections import OrderedDict
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from config import SUPPORTED_TIMEFRAMES, TIMEFRAME_PATTERN
from src_tauri.backend.api.routes.schemas import (
    MarketHeatmapItemResponse,
    MarketHeatmapResponse,
    SignalResponse,
)


def test_active_api_schemas_have_market_and_signal_models():
    assert "timeframe" in SignalResponse.model_fields
    response = MarketHeatmapResponse(
        heatmap=[MarketHeatmapItemResponse(
            symbol="BTCUSDT", market="SPOT", price_change_24h=1.0,
            volume_24h=100.0, price=100.0, regime="UNKNOWN",
        )],
    )
    assert response.heatmap[0].symbol == "BTCUSDT"


def test_list_routes_reject_nonpositive_limits():
    from src_tauri.backend.api.routes import activity, learning, trades

    app = FastAPI()
    app.include_router(trades.router, prefix="/api")
    app.include_router(learning.router, prefix="/api")
    app.include_router(activity.router, prefix="/api")

    with TestClient(app) as client:
        assert client.get("/api/trades?limit=0").status_code == 422
        assert client.get("/api/learning/predictions?limit=0").status_code == 422
        assert client.get("/api/activity?limit=0").status_code == 422


def test_research_delete_routes_validate_identifiers(monkeypatch):
    from src_tauri.backend.api.routes import research

    monkeypatch.setattr(research, "_repo", lambda: pytest.fail("Repository must not be queried"))
    for delete, invalid_id in (
        (research.delete_saved_strategy, "../strategy"),
        (research.delete_backtest_report, "../report"),
        (research.delete_workspace, "../workspace"),
    ):
        with pytest.raises(HTTPException) as error:
            delete(invalid_id)
        assert error.value.status_code == 422


def test_assistant_query_and_timeframe_validation_are_canonical():
    from src_tauri.backend.api.routes.assistant import AssistantQuery

    with pytest.raises(ValidationError):
        AssistantQuery(query="check price", market="UNKNOWN")
    with pytest.raises(ValidationError):
        AssistantQuery(query="check price", symbol="BTC/USDT")
    assert SUPPORTED_TIMEFRAMES == (
        "1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w",
    )
    assert "2h" not in SUPPORTED_TIMEFRAMES
    assert not __import__("re").fullmatch(TIMEFRAME_PATTERN, "2h")


def test_learning_and_evolution_requests_are_typed_and_size_limited():
    from src_tauri.backend.api.routes.evolution import ProposalRequest, WeaknessRequest
    from src_tauri.backend.api.routes.learning import (
        StrategyLabCompareRequest,
        StrategyLabRequest,
    )

    base = {
        "start_date": "2026-01-01T00:00:00Z",
        "end_date": "2026-02-01T00:00:00Z",
    }
    assert StrategyLabRequest(**base).symbol == "BTCUSDT"
    with pytest.raises(ValidationError):
        StrategyLabRequest(**base, unknown="not accepted")
    with pytest.raises(ValidationError):
        StrategyLabCompareRequest(**base, strategies=[])
    oversized = {"blob": "x" * 510_000}
    with pytest.raises(ValidationError):
        StrategyLabRequest(**base, strategy_parameters=oversized)
    with pytest.raises(ValidationError):
        WeaknessRequest(report=oversized)
    with pytest.raises(ValidationError):
        ProposalRequest(
            patch={"safe": True}, candidate_report=oversized,
            rationale="This request exceeds the bounded JSON limit.",
        )


def test_shared_timeframe_pattern_is_used_by_routes(monkeypatch):
    from src_tauri.backend.api.routes import markets

    monkeypatch.setattr(markets, "get_bridge", lambda: pytest.fail("Invalid timeframe must not reach bridge"))
    app = FastAPI()
    app.include_router(markets.router, prefix="/api")
    with TestClient(app) as client:
        response = client.get("/api/markets/analytics/BTCUSDT?timeframe=2h")
    assert response.status_code == 422


def test_request_rate_limit_buckets_are_bounded_and_expired_entries_reclaimable(monkeypatch):
    from src_tauri.backend import main

    monkeypatch.setattr(main, "_MAX_REQUEST_BUCKETS", 2)
    monkeypatch.setattr(main, "_RATE_LIMIT_WINDOW_SECONDS", 10)
    monkeypatch.setattr(main, "_BUCKET_SWEEP_INTERVAL_SECONDS", 5)
    monkeypatch.setattr(main, "_next_bucket_sweep", 0.0)
    main._request_buckets.clear()

    assert not main._rate_limit_exceeded("client-a", 1, now=1)
    assert not main._rate_limit_exceeded("client-b", 1, now=2)
    assert main._rate_limit_exceeded("client-c", 1, now=3)
    assert len(main._request_buckets) == 2
    assert not main._rate_limit_exceeded("client-c", 1, now=12)
    assert len(main._request_buckets) == 1


def test_bridge_caches_evict_oldest_entries(monkeypatch):
    from src_tauri.backend.bridge import orchestrator_bridge

    monkeypatch.setattr(orchestrator_bridge, "_CACHE_MAX_ENTRIES", 2)
    cache = OrderedDict()
    for key in ("first", "second", "third"):
        orchestrator_bridge.OrchestratorBridge._remember_cache(cache, key, key)
    assert list(cache) == ["second", "third"]


@pytest.mark.asyncio
async def test_websocket_manager_unsubscribes_and_queues_without_blocking_event_bus():
    from core.event_bus import EventBus
    from core.event_models import EventType, make_event
    from src_tauri.backend.api.routes.schemas import WebSocketChannel
    from src_tauri.backend.api.websocket.manager import WebSocketManager

    blocked = asyncio.Event()

    class SlowWebSocket:
        async def send_text(self, _message):
            await blocked.wait()

        async def close(self):
            return None

    event_bus = EventBus()
    manager = WebSocketManager(event_bus)
    await manager.start()
    websocket = SlowWebSocket()
    connection_id = manager.connect(websocket)
    manager._subscriptions[WebSocketChannel.PRICE_UPDATES] = {connection_id}
    await asyncio.sleep(0)

    event = make_event(EventType.MARKET_DATA, "test", symbol="BTCUSDT", price=100.0)
    await asyncio.wait_for(manager._on_event(event), timeout=0.1)
    assert manager._outboxes[connection_id].qsize() == 1

    await manager.shutdown()
    assert all(manager._on_event not in handlers for handlers in event_bus._subscribers.values())
    assert not manager._send_tasks


@pytest.mark.asyncio
async def test_health_reports_paper_trading_only_when_enabled_and_available(monkeypatch):
    from src_tauri.backend import main

    class Health:
        @staticmethod
        def get_status():
            return {"status": "healthy", "metrics": {"uptime_seconds": 1.0}}

    orchestrator = SimpleNamespace(
        health_monitor=Health(),
        scanner=SimpleNamespace(_running=True),
        intelligence=SimpleNamespace(predictor=SimpleNamespace(is_trained=True)),
        simulator=None,
    )
    monkeypatch.setattr(main, "orchestrator", orchestrator)
    monkeypatch.setattr(main, "ws_manager", SimpleNamespace(is_running=True))
    monkeypatch.setattr(main, "db", object())
    monkeypatch.setattr(main, "_refresh_runtime_health", lambda: None)
    monkeypatch.setattr(main, "PAPER_TRADING_ENABLED", True)

    assert (await main.health_check())["paper_trading_active"] is False
    orchestrator.simulator = object()
    assert (await main.health_check())["paper_trading_active"] is True
    monkeypatch.setattr(main, "PAPER_TRADING_ENABLED", False)
    assert (await main.health_check())["paper_trading_active"] is False


def test_strategy_weights_use_active_regime():
    from src_tauri.backend.bridge.orchestrator_bridge import OrchestratorBridge

    selector = SimpleNamespace(
        weights={"trend_following": 1.0, "mean_reversion": 1.0},
        regime_prefs={
            "BULL_TREND": {"trend_following": 1.5},
            "SIDEWAYS": {"mean_reversion": 1.5},
        },
    )
    bridge = object.__new__(OrchestratorBridge)
    bridge.orch = SimpleNamespace(
        intelligence=SimpleNamespace(strategy_selector=selector),
        _current_regime="SIDEWAYS",
    )

    weights = bridge.get_strategy_weights()
    assert weights["trend_following"]["regime_adjusted"] == 1.0
    assert weights["mean_reversion"]["regime_adjusted"] == 1.5


def test_orchestrator_tracks_latest_signal_regime():
    from core.orchestrator import Orchestrator

    orchestrator = SimpleNamespace(_current_regime="UNKNOWN")
    Orchestrator._update_current_regime(orchestrator, {"regime": "SIDEWAYS"})

    assert orchestrator._current_regime == "SIDEWAYS"


@pytest.mark.asyncio
async def test_remote_mode_allows_non_loopback_websocket_with_token(monkeypatch):
    from src_tauri.backend import main

    class Manager:
        connected = False

        def connect(self, _websocket):
            self.connected = True

        async def handle_message(self, _websocket, _message):
            return None

        def disconnect(self, _websocket):
            self.connected = False

    class RemoteWebSocket:
        client = SimpleNamespace(host="203.0.113.20")
        application_state = None

        def __init__(self):
            self.accepted = False
            self.closed = []
            self.sent = []
            self.messages = iter([
                json.dumps({"type": "authenticate", "token": "valid-remote-token"}),
            ])

        async def accept(self):
            self.accepted = True

        async def receive_text(self):
            try:
                return next(self.messages)
            except StopIteration:
                raise WebSocketDisconnect(code=1000)

        async def send_json(self, message):
            self.sent.append(message)

        async def close(self, code, reason):
            self.closed.append((code, reason))

    monkeypatch.setattr(main, "_REMOTE_API_ENABLED", True)
    monkeypatch.setattr(main, "_api_token", "valid-remote-token")
    monkeypatch.setattr(main, "_request_buckets", OrderedDict())
    monkeypatch.setattr(main, "_next_bucket_sweep", 0.0)
    manager = Manager()
    monkeypatch.setattr(main, "ws_manager", manager)
    websocket = RemoteWebSocket()

    await main.websocket_endpoint(websocket)

    assert websocket.accepted
    assert websocket.sent == [{"type": "authenticated"}]
    assert not websocket.closed
    assert not manager.connected


@pytest.mark.asyncio
async def test_multi_tool_assistant_results_are_sent_for_provider_interpretation(monkeypatch):
    from src_tauri.backend import assistant_runtime

    captured = []

    async def interpret(_query, evidence):
        captured.append(evidence)
        return "Combined interpretation"

    monkeypatch.setattr(
        assistant_runtime,
        "get_runtime_intelligence_config",
        lambda: SimpleNamespace(provider_enabled=True, max_tool_calls=3, mode=SimpleNamespace(value="hybrid")),
    )
    monkeypatch.setattr(assistant_runtime, "optional_provider_interpretation", interpret)

    class Bridge:
        @staticmethod
        def get_market_snapshot(symbol, market):
            return {
                "symbol": symbol, "market": market, "price": 50.0,
                "price_change_24h": 0.0, "regime": "UNKNOWN",
                "data_freshness": "LIVE", "data_age_seconds": 0,
            }

        @staticmethod
        def get_risk_metrics():
            return {"exposure": 0.0, "risk_status": "within_limits"}

    result = await assistant_runtime.execute_assistant_query(
        Bridge(), "show market snapshot and risk status", "BTCUSDT", "SPOT", "1h",
    )

    assert len(captured) == 1
    assert len(captured[0]["results"]) == 2
    assert "Combined interpretation" in result.answer


def test_relevant_memory_beyond_first_twenty_rows_is_retrieved(tmp_path):
    from database.connection import Database
    from database.repositories import Repository
    from src_tauri.backend.assistant_memory import build_memory_record, retrieve_relevant_memories

    database = Database(f"sqlite:///{tmp_path / 'old-memory.db'}")
    database.init_db()
    repository = Repository(database.session_maker())
    relevant = build_memory_record(
        owner_key="owner-a", memory_type="semantic",
        content="Remember I prefer detailed BTC market analysis", importance=0.1,
    )
    repository.save_assistant_memory(relevant)
    for index in range(25):
        repository.save_assistant_memory(build_memory_record(
            owner_key="owner-a", memory_type="semantic",
            content=f"Unrelated note number {index:02d}", importance=1.0,
        ))

    memories = retrieve_relevant_memories(repository, "owner-a", "BTC market analysis", limit=3)
    database.close()

    assert memories
    assert memories[0]["memory_id"] == relevant["memory_id"]
