"""Structured, redacted application logging helpers."""
from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|credential)\b\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(\btoken\b\s*[:=]\s*)[^\s,;]+"),
)


def redact_sensitive_text(value: str) -> str:
    """Redact common secret assignments before they reach a log sink."""
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(r"\1[REDACTED]", result)
    return result


class JsonLogFormatter(logging.Formatter):
    """Emit one compact JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
        }
        for key in ("event", "request_id", "method", "path", "status_code", "duration_ms", "component", "operation", "symbol", "market", "order_type", "reason", "scanner_state", "symbols_selected", "refresh_successes", "refresh_failures", "refresh_skipped", "feature", "function", "phase", "trace_id", "error_type", "detail", "count", "enabled", "screen", "source", "level_name"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_structured_logging(level: str = "INFO") -> None:
    """Configure a structured root handler without duplicating existing handlers."""
    root = logging.getLogger()
    numeric_level = getattr(logging, str(level).upper(), logging.INFO)
    root.setLevel(numeric_level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(JsonLogFormatter())


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Write a structured event; fields should be bounded and non-sensitive."""
    safe_fields = {
        key: value for key, value in fields.items()
        if key.lower() not in {"token", "password", "secret", "authorization", "api_key", "access_token", "refresh_token", "credential"}
    }
    logger.log(level, event, extra={"event": event, **safe_fields})


# Runtime Python function tracing is deliberately opt-in: it is extremely verbose.
_TRACE_LOCK = threading.Lock()
_TRACE_ENABLED = False
_TRACE_LOCAL = threading.local()
_TRACE_ROOT = Path(__file__).resolve().parents[1]
_TRACE_LOGGER = logging.getLogger("blackmarket.function_trace")
_TRACE_SKIP = {"observability.py"}


def function_trace_enabled() -> bool:
    return _TRACE_ENABLED


def _is_application_frame(frame) -> bool:
    try:
        path = Path(frame.f_code.co_filename).resolve()
        if not path.is_relative_to(_TRACE_ROOT):
            return False
        if path.name in _TRACE_SKIP or "tests" in path.parts or "__pycache__" in path.parts:
            return False
        if frame.f_code.co_name.startswith("__") and frame.f_code.co_name.endswith("__"):
            return False
        return True
    except (OSError, ValueError):
        return False


def _function_profile(frame, event, arg):
    if getattr(_TRACE_LOCAL, "busy", False) or not _TRACE_ENABLED:
        return
    if event not in ("call", "return"):
        return
    if not _is_application_frame(frame):
        return
    _TRACE_LOCAL.busy = True
    try:
        frame_key = id(frame)
        now = time.perf_counter()
        starts = getattr(_TRACE_LOCAL, "starts", None)
        if starts is None:
            starts = {}
            _TRACE_LOCAL.starts = starts
        if event == "call":
            starts[frame_key] = now
            log_event(
                _TRACE_LOGGER, logging.INFO, "python_function_call",
                component="python", function=frame.f_code.co_name,
                detail=f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno}",
                phase="call",
            )
        else:
            started = starts.pop(frame_key, now)
            log_event(
                _TRACE_LOGGER, logging.INFO, "python_function_return",
                component="python", function=frame.f_code.co_name,
                detail=f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno}",
                phase="return_or_yield", duration_ms=round((now - started) * 1000, 3),
            )
    except Exception:
        # Diagnostic instrumentation must never interfere with application execution.
        pass
    finally:
        _TRACE_LOCAL.busy = False


def set_function_trace_enabled(enabled: bool) -> bool:
    """Enable/disable app-source Python call/return tracing for this backend process."""
    global _TRACE_ENABLED
    requested = bool(enabled)
    with _TRACE_LOCK:
        if requested == _TRACE_ENABLED:
            return _TRACE_ENABLED
        _TRACE_ENABLED = requested
        if requested:
            sys.setprofile(_function_profile)
            threading.setprofile(_function_profile)
        else:
            sys.setprofile(None)
            threading.setprofile(None)
    log_event(
        logging.getLogger("blackmarket.diagnostics"), logging.WARNING if requested else logging.INFO,
        "python_function_trace_changed", component="diagnostics", enabled=requested,
        detail="Function tracing records app-source calls and returns; it can generate large logs.",
    )
    return _TRACE_ENABLED
