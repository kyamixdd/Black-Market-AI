"""FastAPI Backend Adapter for BlackMarket AI Desktop Application."""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import logging
import os
import sys
import time
from collections import defaultdict, deque
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
config_path = config_dir / ".env"
load_dotenv(config_path if config_path.is_file() else PROJECT_ROOT / ".env")

from config import DATABASE_URL, LOG_LEVEL
from core.config_validator import validate_config_or_exit
from core.orchestrator import Orchestrator
from database.connection import Database

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
_tauri_origins = ["http://tauri.localhost", "https://tauri.localhost", "tauri://localhost", *_ALLOWED_ORIGINS]
if os.environ.get("BLACKMARKET_DESKTOP_DEV") == "1":
    _tauri_origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])


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
    if _REMOTE_API_ENABLED:
        if not _api_token:
            raise RuntimeError("BLACKMARKET_API_TOKEN is required when remote API mode is enabled.")
        if host not in {"0.0.0.0", "::"} and not _is_loopback(host):
            raise RuntimeError("Remote API host must be 0.0.0.0, ::, or loopback.")
        return host
    if not _is_loopback(host):
        raise RuntimeError("BLACKMARKET_API_HOST must be a loopback IP address unless remote API mode is explicitly enabled.")
    return host


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global orchestrator, db, bridge, ws_manager
    event_task: asyncio.Task | None = None
    orchestrator_task: asyncio.Task | None = None

    logger.info("Starting BlackMarket AI Backend Adapter...")

    # Validate configuration
    validate_config_or_exit()

    # Initialize database
    db = Database(DATABASE_URL)
    db.init_db()
    integrity = db.integrity_check()
    if integrity.lower() != "ok":
        raise RuntimeError(f"SQLite database integrity check failed: {integrity}")

    # Create orchestrator
    orchestrator = Orchestrator(db)
    await orchestrator.initialize()

    # Create bridge
    bridge = get_bridge(orchestrator)

    # Create WebSocket manager
    ws_manager = WebSocketManager(orchestrator.event_bus)
    await ws_manager.start()
    event_task = asyncio.create_task(orchestrator.event_bus.run(), name="blackmarket-event-bus")
    orchestrator_task = asyncio.create_task(orchestrator.run(), name="blackmarket-orchestrator")

    logger.info("BlackMarket AI Backend Adapter started")

    try:
        yield
    finally:
        logger.info("Shutting down BlackMarket AI Backend Adapter...")
        if orchestrator:
            await orchestrator.stop()
        if orchestrator_task and not orchestrator_task.done():
            orchestrator_task.cancel()
            await asyncio.gather(orchestrator_task, return_exceptions=True)
        if event_task and not event_task.done():
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
        if ws_manager:
            await ws_manager.shutdown()
        if db:
            db.close()
        logger.info("BlackMarket AI Backend Adapter stopped")


app = FastAPI(
    title="BlackMarket AI API",
    description="Local autonomous market research and paper trading API",
    version="1.0.0",
    lifespan=lifespan,
)


_request_buckets: dict[str, deque[float]] = defaultdict(deque)
_RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.environ.get("BLACKMARKET_RATE_LIMIT_WINDOW_SECONDS", "60")))
_API_RATE_LIMIT = max(10, int(os.environ.get("BLACKMARKET_API_RATE_LIMIT", "120")))
_LOGIN_RATE_LIMIT = max(3, int(os.environ.get("BLACKMARKET_LOGIN_RATE_LIMIT", "10")))


def _rate_limit_exceeded(key: str, limit: int, now: float | None = None) -> bool:
    """Fixed-window sliding counter; process-local protection for a single API worker."""
    current = time.monotonic() if now is None else now
    bucket = _request_buckets[key]
    cutoff = current - _RATE_LIMIT_WINDOW_SECONDS
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(current)
    return False


@app.middleware("http")
async def require_local_api_auth(request: Request, call_next):
    client_host = request.client.host if request.client else "unknown"
    if request.url.path.startswith("/api/") and _rate_limit_exceeded(f"api:{client_host}", _API_RATE_LIMIT):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}, headers={"Retry-After": str(_RATE_LIMIT_WINDOW_SECONDS)})

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
    """Authenticated Server-Sent Events stream for browser dashboard clients."""
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Backend is starting")
    event_bus = orchestrator.event_bus
    queue: asyncio.Queue = asyncio.Queue(maxsize=512)

    async def on_event(event):
        try:
            queue.put_nowait(event.to_dict())
        except asyncio.QueueFull:
            # Keep the newest dashboard state without blocking the trading event bus.
            try:
                queue.get_nowait()
                queue.task_done()
                queue.put_nowait(event.to_dict())
            except (asyncio.QueueEmpty, asyncio.QueueFull):
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
    if _rate_limit_exceeded(f"ws:{client_host}", 30):
        await websocket.close(code=4429, reason="WebSocket connection rate limit exceeded")
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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
            "database_connected": db is not None,
            "market_data_active": False,
            "learning_active": False,
            "paper_trading_active": False,
            "uptime_seconds": 0.0,
            "version": "1.0.0",
        }
    health = orchestrator.health_monitor.get_status()
    return {
        "status": health.get("status", "unknown"),
        "backend_ready": True,
        "websocket_connected": bool(ws_manager and ws_manager.get_stats().get("running")),
        "database_connected": db is not None,
        "market_data_active": orchestrator.scanner._running,
        "learning_active": orchestrator.intelligence.predictor.is_trained,
        "paper_trading_active": True,
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
async def global_exception_handler(request: Request, exc: Exception):
    """Log diagnostic details locally without exposing them to API clients."""
    logger.exception(
        "Unhandled API exception for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
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