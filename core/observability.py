"""Structured, redacted application logging helpers."""
from __future__ import annotations

import json
import inspect
import functools
import contextvars
import uuid
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


_SENSITIVE_FIELD_NAMES = {"token", "password", "secret", "authorization", "api_key", "access_token", "refresh_token", "credential"}


def sanitize_log_value(value: Any, field_name: str = "") -> Any:
    """Redact sensitive assignments recursively from structured log values."""
    if field_name.lower() in _SENSITIVE_FIELD_NAMES:
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_sensitive_text(value)[:2000]
    if isinstance(value, dict):
        return {
            str(key)[:120]: sanitize_log_value(item, str(key))
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_log_value(item) for item in value[:100]]
    return value


class JsonLogFormatter(logging.Formatter):
    """Emit one compact JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
        }
        for key in ("event", "request_id", "method", "path", "status_code", "duration_ms", "component", "operation", "symbol", "market", "order_type", "reason", "scanner_state", "symbols_selected", "refresh_successes", "refresh_failures", "refresh_skipped", "feature", "function", "phase", "trace_id", "error_type", "detail", "count", "enabled", "screen", "source", "level_name", "root_cause", "suggested_fix", "input_count", "output_count", "state", "step", "data_age_ms", "stale", "result_summary", "operation_id", "eligible_count", "candidate_count", "selected_count", "filtered_count", "decision", "position_id", "model_status", "learning_updates", "paper_mode", "exchange_client", "source_count", "invalid_count", "feature_count", "render_phase", "render_duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = sanitize_log_value(value, key)
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
    """Write a structured event; add a heuristic repair hint to error events."""
    if level >= logging.ERROR:
        diagnostic_text = fields.get("detail") or fields.get("error_type") or event
        root_cause, suggested_fix = recommend_diagnostic_fix(str(diagnostic_text))
        fields.setdefault("root_cause", root_cause)
        fields.setdefault("suggested_fix", suggested_fix)
        fields.setdefault("trace_id", _OPERATION_TRACE_ID.get() or "")
    safe_fields = {
        key: sanitize_log_value(value, key)
        for key, value in fields.items()
        if key.lower() not in _SENSITIVE_FIELD_NAMES
    }
    logger.log(level, event, extra={"event": event, **safe_fields})


_OPERATION_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("blackmarket_operation_trace_id", default=None)


def recommend_diagnostic_fix(error: BaseException | str) -> tuple[str, str]:
    """Heuristic root cause and next step; not a definitive diagnosis."""
    message = str(error)
    text = message.lower()
    if isinstance(error, TimeoutError) or "timeout" in text or "timed out" in text:
        return "A dependency or operation exceeded its time limit.", "Check service readiness, exchange/API latency and timeout configuration; retry only idempotent operations."
    if "connection" in text or "network" in text or "connect" in text:
        return "A network or local backend connection could not be established.", "Check the backend supervisor, host/port, exchange connectivity, DNS and firewall."
    if "rate limit" in text or "429" in text:
        return "The upstream or local API rate limit was reached.", "Reduce request frequency, verify the rate limiter and honor Retry-After/backoff."
    if "database" in text or "sqlite" in text or "sqlalchemy" in text or "locked" in text:
        return "A database operation failed or the database was unavailable.", "Check database health, disk space, transaction rollback and SQLite lock contention; inspect the traceback."
    if "permission" in text or "unauthorized" in text or "forbidden" in text or "401" in text or "403" in text:
        return "The operation was rejected by authorization or permission checks.", "Verify the authenticated desktop session and required permission; do not bypass the guard."
    if "invalid" in text or "validation" in text or "valueerror" in text:
        return "Input or returned data did not satisfy validation rules.", "Inspect the event schema and upstream payload; correct the source data or validation contract."
    if "model" in text or "predict" in text or "training" in text:
        return "The model pipeline failed or the active model/data contract is incompatible.", "Check model artifact integrity, feature order/version, training data availability and validation/promotion status."
    return "The operation raised an exception; inspect the correlated exception and stack trace.", "Filter by trace_id, inspect preceding events and reproduce with the same inputs and runtime state."


def traced_operation(feature: str, component: str = "application"):
    """Log correlated start/completion/failure events for important operations."""
    def decorate(function):
        name = function.__qualname__
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def async_wrapper(*args, **kwargs):
                trace_id = _OPERATION_TRACE_ID.get() or uuid.uuid4().hex
                token = _OPERATION_TRACE_ID.set(trace_id)
                started = time.perf_counter()
                log_event(_TRACE_LOGGER, logging.INFO, "operation_started", component=component, feature=feature, function=name, phase="start", trace_id=trace_id)
                try:
                    result = await function(*args, **kwargs)
                except Exception as exc:
                    root, fix = recommend_diagnostic_fix(exc)
                    log_event(_TRACE_LOGGER, logging.ERROR, "operation_failed", component=component, feature=feature, function=name, phase="failure", trace_id=trace_id, error_type=type(exc).__name__, root_cause=root, suggested_fix=fix, detail=f"{type(exc).__name__}: {exc}", duration_ms=round((time.perf_counter()-started)*1000,3))
                    raise
                else:
                    log_event(_TRACE_LOGGER, logging.INFO, "operation_completed", component=component, feature=feature, function=name, phase="complete", trace_id=trace_id, duration_ms=round((time.perf_counter()-started)*1000,3))
                    return result
                finally:
                    _OPERATION_TRACE_ID.reset(token)
            return async_wrapper
        @functools.wraps(function)
        def sync_wrapper(*args, **kwargs):
            trace_id = _OPERATION_TRACE_ID.get() or uuid.uuid4().hex
            token = _OPERATION_TRACE_ID.set(trace_id)
            started = time.perf_counter()
            log_event(_TRACE_LOGGER, logging.INFO, "operation_started", component=component, feature=feature, function=name, phase="start", trace_id=trace_id)
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                root, fix = recommend_diagnostic_fix(exc)
                log_event(_TRACE_LOGGER, logging.ERROR, "operation_failed", component=component, feature=feature, function=name, phase="failure", trace_id=trace_id, error_type=type(exc).__name__, root_cause=root, suggested_fix=fix, detail=f"{type(exc).__name__}: {exc}", duration_ms=round((time.perf_counter()-started)*1000,3))
                raise
            else:
                log_event(_TRACE_LOGGER, logging.INFO, "operation_completed", component=component, feature=feature, function=name, phase="complete", trace_id=trace_id, duration_ms=round((time.perf_counter()-started)*1000,3))
                return result
            finally:
                _OPERATION_TRACE_ID.reset(token)
        return sync_wrapper
    return decorate


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
        if path.name in _TRACE_SKIP or any(part in {"tests", "__pycache__", ".venv", "venv", "site-packages", "dist-packages", "node_modules", "build", "dist", "target"} for part in path.parts):
            return False
        if frame.f_code.co_name.startswith("__") and frame.f_code.co_name.endswith("__"):
            return False
        return True
    except (OSError, ValueError):
        return False


def _function_profile(frame, event, arg):
    if getattr(_TRACE_LOCAL, "busy", False) or not _TRACE_ENABLED:
        return
    if event not in ("call", "return", "exception"):
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
        elif event == "exception":
            exception_type, exception_value, _ = arg
            log_event(
                _TRACE_LOGGER, logging.ERROR, "python_function_exception",
                component="python", function=frame.f_code.co_name,
                detail=f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno} · {exception_type.__name__}: {exception_value}",
                phase="exception", error_type=exception_type.__name__, root_cause=recommend_diagnostic_fix(exception_value)[0], suggested_fix=recommend_diagnostic_fix(exception_value)[1], trace_id=_OPERATION_TRACE_ID.get() or "",
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
