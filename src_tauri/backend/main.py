"""FastAPI Backend Adapter for BlackMarket AI Desktop Application."""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.websockets import WebSocketState

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv

config_dir = Path(os.environ.get("BLACKMARKET_CONFIG_DIR", PROJECT_ROOT))
config_path = Path(os.environ.get("BLACKMARKET_ENV_FILE", config_dir / ".env"))
if not config_path.is_file():
    config_path = PROJECT_ROOT / ".env"
load_dotenv(config_path if config_path.is_file() else None)

from config import APP_ENV, DATABASE_URL, LOG_LEVEL
from core.config_validator import validate_config_or_exit
from core.orchestrator import Orchestrator
from database.connection import Database
from database.repositories import Repository

from src_tauri.backend.api.routes import (
    markets,
    signals,
    portfolio,
    positions,
    trades,
    intelligence,
    learning,
    risk,
    activity,
    settings,
)
from src_tauri.backend.api.routes.schemas import (
    HealthResponse,
    SystemHealthResponse,
)
from src_tauri.backend.api.websocket.manager import WebSocketManager
from src_tauri.backend.bridge.orchestrator_bridge import get_bridge

logger = logging.getLogger(__name__)

# Global instances
orchestrator: Orchestrator | None = None
db: Database | None = None
bridge: "OrchestratorBridge" | None = None
ws_manager: WebSocketManager | None = None
_shutdown_token = os.environ.get("BLACKMARKET_SHUTDOWN_TOKEN")
_api_token = os.environ.get("BLACKMARKET_API_TOKEN")
_REMOTE_API_ENABLED = os.environ.get("BLACKMARKET_REMOTE_API_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
_ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("BLACKMARKET_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
_request_server_shutdown: Callable[[], None] | None = None
_tauri_origins = ["http://tauri.localhost", "tauri://localhost", *_ALLOWED_ORIGINS]
if os.environ.get("BLACKMARKET_DESKTOP_DEV") == "1":
    _tauri_origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])




def _apply_persisted_settings(database: Database) -> None:
    """Load persisted operator settings before constructing runtime services."""
    import config
    from core import orchestrator as orchestrator_module
    from market import scanner as scanner_module
    from intelligence import intelligence_core as intelligence_module
    from paper_trading import simulator as simulator_module

    from src_tauri.backend.api.routes.schemas import SettingsRequest

    stored_settings = Repository(database.session_maker()).get_app_settings()
    try:
        settings = SettingsRequest.model_validate(stored_settings).model_dump(exclude_none=True)
    except Exception as exc:
        raise RuntimeError("Persisted application settings failed validation; refusing unsafe startup.") from exc
    if settings.get("spot_enabled", config.SPOT_ENABLED) is False and settings.get(
        "futures_enabled", config.USDM_FUTURES_ENABLED
    ) is False:
        raise RuntimeError("Persisted settings disable both markets; refusing startup.")
    if settings.get("risk_per_trade_pct", config.RISK_PER_TRADE_PCT) > settings.get(
        "risk_max_total_open_pct", config.RISK_MAX_TOTAL_OPEN_PCT
    ):
        raise RuntimeError("Persisted risk settings are inconsistent; refusing startup.")
    if settings.get("telegram_enabled", config.TELEGRAM_ENABLED) and not (
        config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID
    ):
        raise RuntimeError("Persisted settings enable Telegram without configured credentials.")
    targets = {
        "spot_enabled": ("SPOT_ENABLED", bool, (config, orchestrator_module, scanner_module)),
        "futures_enabled": ("USDM_FUTURES_ENABLED", bool, (config, orchestrator_module, scanner_module)),
        "scan_all_eligible_symbols": ("SCAN_ALL_ELIGIBLE_SYMBOLS", bool, (config, orchestrator_module)),
        "timeframes": ("TIMEFRAMES", list, (config, orchestrator_module, intelligence_module)),
        "spot_initial_balance": ("SPOT_INITIAL_BALANCE", float, (config, simulator_module)),
        "futures_initial_balance": ("FUTURES_INITIAL_BALANCE", float, (config, simulator_module)),
        "risk_per_trade_pct": ("RISK_PER_TRADE_PCT", float, (config, simulator_module)),
        "risk_max_daily_loss_pct": ("RISK_MAX_DAILY_LOSS_PCT", float, (config, simulator_module)),
        "risk_max_total_open_pct": ("RISK_MAX_TOTAL_OPEN_PCT", float, (config, simulator_module)),
        "risk_max_leverage": ("RISK_MAX_LEVERAGE", float, (config, simulator_module)),
        "max_spot_positions": ("MAX_SPOT_POSITIONS", int, (config, simulator_module)),
        "max_futures_positions": ("MAX_FUTURES_POSITIONS", int, (config, simulator_module)),
        "telegram_enabled": ("TELEGRAM_ENABLED", bool, (config, orchestrator_module)),
    }
    for key, (attribute, cast, modules) in targets.items():
        if key not in settings:
            continue
        value = cast(settings[key])
        for module in modules:
            setattr(module, attribute, value)

def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _matches_bearer_token(authorization: str | None, expected: str | None) -> bool:
    if not expected:
        return False
    scheme, separator, supplied_token = (authorization or "").partition(" ")
    return (
        scheme.lower() == "bearer"
        and bool(separator)
        and supplied_token.isascii()
        and hmac.compare_digest(supplied_token, expected)
    )


def _api_host() -> str:
    host = os.environ.get("BLACKMARKET_API_HOST", "127.0.0.1")
    if _REMOTE_API_ENABLED and host in {"0.0.0.0", "::"}:
        return host
    if not _is_loopback(host):
        raise RuntimeError("BLACKMARKET_API_HOST must be loopback unless remote API mode is explicitly enabled.")
    return host


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with cleanup for partial startup failures."""
    global orchestrator, db, bridge, ws_manager
    orchestrator_task: asyncio.Task | None = None

    logger.info("Starting BlackMarket AI Backend Adapter...")
    try:
        # Validate configuration before opening external resources.
        validate_config_or_exit()

        # Hosted production must use durable PostgreSQL, never ephemeral SQLite.
        if APP_ENV == "production" and DATABASE_URL.startswith("sqlite"):
            raise RuntimeError("Production requires a durable PostgreSQL DATABASE_URL; SQLite is not supported for hosted production.")
        # Initialize and verify the database before constructing services.
        db = Database(DATABASE_URL)
        db.init_db()
        _apply_persisted_settings(db)
        integrity = db.integrity_check()
        if integrity.lower() != "ok":
            raise RuntimeError(f"Database integrity check failed: {integrity}")

        # Initialize the trading engine and local API adapters.
        orchestrator = Orchestrator(db)
        await orchestrator.initialize()
        bridge = get_bridge(orchestrator)

        ws_manager = WebSocketManager(orchestrator.event_bus)
        await ws_manager.start()
        orchestrator_task = asyncio.create_task(
            orchestrator.run(), name="blackmarket-orchestrator"
        )

        logger.info("BlackMarket AI Backend Adapter started")
        yield
    finally:
        logger.info("Shutting down BlackMarket AI Backend Adapter...")
        # Each cleanup stage is isolated so a failure cannot prevent the
        # remaining clients and the database from being released.
        if orchestrator is not None:
            try:
                await orchestrator.stop()
            except Exception:
                logger.exception("Orchestrator shutdown failed")
        if orchestrator_task is not None and not orchestrator_task.done():
            orchestrator_task.cancel()
            await asyncio.gather(orchestrator_task, return_exceptions=True)
        if ws_manager is not None:
            try:
                await ws_manager.shutdown()
            except Exception:
                logger.exception("Dashboard WebSocket shutdown failed")
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Database shutdown failed")
        orchestrator = None
        bridge = None
        ws_manager = None
        db = None
        logger.info("BlackMarket AI Backend Adapter stopped")


app = FastAPI(
    title="BlackMarket AI API",
    description="Local autonomous market research and paper trading API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_local_api_auth(request: Request, call_next):
    client_host = request.client.host if request.client else None
    if not _is_loopback(client_host) and not _REMOTE_API_ENABLED:
        return JSONResponse(status_code=403, content={"detail": "Remote API access is disabled"})

    if request.url.path == "/api" or request.url.path.startswith("/api/"):
        if request.method != "OPTIONS":
            if not _api_token:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Local API authentication is not configured"},
                )
            if not _matches_bearer_token(
                request.headers.get("authorization"),
                _api_token,
            ):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


for router in (
    markets.router,
    signals.router,
    portfolio.router,
    positions.router,
    trades.router,
    intelligence.router,
    learning.router,
    risk.router,
    activity.router,
    settings.router,
):
    app.include_router(router, prefix="/api")


@app.get("/api/events/stream")
async def event_stream():
    """Authenticated Server-Sent Events stream for browser clients."""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Backend is starting")
    event_bus = orchestrator.event_bus
    queue: asyncio.Queue = asyncio.Queue(maxsize=512)

    async def on_event(event):
        try:
            queue.put_nowait(event.to_dict())
        except asyncio.QueueFull:
            # Drop the oldest dashboard update rather than blocking trading.
            try:
                queue.get_nowait()
                queue.task_done()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event.to_dict())
            except asyncio.QueueFull:
                logger.warning("Dropping dashboard SSE event because its queue is full")

    event_bus.subscribe_all(on_event)

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield "data: " + json.dumps(event, default=str, separators=(",", ":")) + "\n\n"
                    queue.task_done()
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            subscribers = event_bus._subscribers.get("*", [])
            if on_event in subscribers:
                subscribers.remove(on_event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else None
    if not _is_loopback(client_host):
        await websocket.close(code=4403, reason="Loopback clients only")
        return
    if not _api_token:
        await websocket.close(code=1011, reason="Local API authentication is not configured")
        return

    manager = ws_manager
    if manager is None:
        await websocket.close(code=1013, reason="Backend is starting")
        return
    await websocket.accept()
    connected = False
    try:
        authentication = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        try:
            request = json.loads(authentication)
        except json.JSONDecodeError:
            request = None
        token = request.get("token") if isinstance(request, dict) else None
        if (
            not isinstance(request, dict)
            or request.get("type") != "authenticate"
            or not isinstance(token, str)
            or not token.isascii()
            or not hmac.compare_digest(token, _api_token)
        ):
            await websocket.close(code=4401, reason="Authentication required")
            return

        manager.connect(websocket)
        connected = True
        await websocket.send_json({"type": "authenticated"})
        while True:
            data = await websocket.receive_text()
            await manager.handle_message(websocket, data)
    except asyncio.TimeoutError:
        await websocket.close(code=4408, reason="Authentication timed out")
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
    except RuntimeError:
        if websocket.application_state is not WebSocketState.DISCONNECTED:
            raise
        logger.debug("WebSocket client disconnected after a failed send")
    finally:
        if connected:
            manager.disconnect(websocket)

# The desktop origins are fixed; the Vite origin is enabled only for Tauri dev builds.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_tauri_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    if orchestrator is None:
        return {
            "status": "starting",
            "backend_ready": False,
            "websocket_connected": False,
            "database_connected": bool(db and db.health().get("status") == "ok"),
            "market_data_active": False,
            "learning_active": False,
            "paper_trading_active": False,
            "uptime_seconds": 0.0,
            "version": "1.0.0",
        }
    health = orchestrator.health_monitor.get_status()
    from config import AUTO_MODEL_TRAINING, PAPER_TRADING_ENABLED
    database_connected = bool(db and db.health().get("status") == "ok")
    market_data_active = bool(
        orchestrator.scanner._running and orchestrator.has_fresh_market_data()
    )
    last_ws_message_at = getattr(orchestrator, "_last_ws_message_at", None)
    exchange_ws_connected = (
        last_ws_message_at is not None
        and asyncio.get_running_loop().time() - last_ws_message_at < 120
    )
    return {
        "status": health.get("status", "unknown"),
        # API/database readiness is independent of exchange availability.
        # Market data is reported separately so a provider outage does not
        # make the hosted control plane inaccessible.
        "backend_ready": bool(database_connected and orchestrator is not None),
        # This is the local dashboard WebSocket service. Exchange market
        # stream health is reported separately so REST-only fallback stays usable.
        "websocket_connected": bool(ws_manager and ws_manager.get_stats().get("running")),
        "exchange_websocket_connected": exchange_ws_connected,
        "database_connected": database_connected,
        "market_data_active": market_data_active,
        "learning_active": bool(AUTO_MODEL_TRAINING and any(
            task.get_name() == "blackmarket-learning" and not task.done()
            for task in asyncio.all_tasks()
        )),
        "paper_trading_active": PAPER_TRADING_ENABLED,
        "uptime_seconds": health.get("metrics", {}).get("uptime_seconds", 0.0),
        "version": "1.0.0",
    }


@app.post("/_internal/shutdown")
async def shutdown_backend(authorization: str | None = Header(default=None)):
    """Request graceful shutdown from the owning desktop process only."""
    if not _shutdown_token:
        raise HTTPException(status_code=404, detail="Not found")

    scheme, separator, supplied_token = (authorization or "").partition(" ")
    if (
        scheme.lower() != "bearer"
        or not separator
        or not hmac.compare_digest(supplied_token, _shutdown_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid shutdown authorization")

    if _request_server_shutdown is None:
        raise HTTPException(status_code=503, detail="Backend server is not ready to shut down")

    _request_server_shutdown()
    return {"status": "shutting_down"}


@app.get("/api/system/status", response_model=SystemHealthResponse)
async def system_status():
    """Get system status."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    health = orchestrator.health_monitor.get_status()
    return {
        "status": health.get("status", "unknown"),
        "components": health.get("components", {}),
        "metrics": health.get("metrics", {}),
        "uptime_seconds": health.get("metrics", {}).get("uptime_seconds", 0),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=_api_host(),
            port=int(os.environ.get("BLACKMARKET_API_PORT", "8765")),
            reload=False,
            log_level=LOG_LEVEL.lower(),
        )
    )
    _request_server_shutdown = lambda: setattr(server, "should_exit", True)
    try:
        server.run()
    finally:
        _request_server_shutdown = None