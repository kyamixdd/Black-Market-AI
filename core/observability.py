"""Structured, redacted application logging helpers."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter
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
        for key in (
            "event", "request_id", "method", "path", "endpoint", "status_code",
            "duration_ms", "component", "operation", "symbol", "market",
            "order_type", "reason", "recommendation", "details", "outcome",
            "phase", "state", "scanner_state", "symbols_selected",
            "refresh_successes", "refresh_failures", "refresh_skipped",
            "symbol_count", "eligible_count", "candidate_count", "signal_count",
            "timeframe_count", "failed_count", "skipped_count", "labeled_count",
            "online_updates", "handler_count", "error_type",
            "exception_type", "frontend_event_id", "table", "query_type",
            "affected_rows", "event_type", "handler", "queue_capacity",
            "dropped_count",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact_sensitive_text(value) if isinstance(value, str) else value
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
        key: redact_sensitive_text(value) if isinstance(value, str) else value
        for key, value in fields.items()
        if key.lower() not in {"token", "password", "secret", "authorization", "api_key", "access_token", "refresh_token", "credential"}
    }
    logger.log(level, event, extra={"event": event, **safe_fields})


_WRITE_STATEMENT = re.compile(
    r"^\s*(?P<operation>INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE
)
_WRITE_TABLE = re.compile(
    r"\b(?:INTO|UPDATE|FROM)\s+[\"`\[]?(?P<table>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


class SQLWriteObserver:
    """Aggregate successful writes while reporting failed statements immediately."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window_started = time.monotonic()
        self._window_counts: Counter[str] = Counter()
        self._window_duration_ms = 0.0
        self._window_failed = 0
        self._total_successful = 0
        self._total_failed = 0
        self._by_table: Counter[str] = Counter()
        self._last_write_at: str | None = None
        self._last_error_at: str | None = None

    def record_success(self, operation: str, table: str, duration_ms: float, row_count: int | None) -> None:
        with self._lock:
            key = f"{operation} {table}"
            self._window_counts[key] += 1
            self._window_duration_ms += duration_ms
            self._total_successful += 1
            self._by_table[table] += max(0, row_count or 0)
            self._last_write_at = datetime.now(timezone.utc).isoformat()
        self.flush()

    def flush(self, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            if not self._window_counts and not self._window_failed:
                return
            if not force and now - self._window_started < 10:
                return
            details = "; ".join(
                f"{item} x{count}" for item, count in sorted(self._window_counts.items())
            )
            window_duration = self._window_duration_ms
            failed = self._window_failed
            self._window_counts.clear()
            self._window_duration_ms = 0.0
            self._window_failed = 0
            self._window_started = now
        log_event(
            logging.getLogger("database.write"),
            logging.INFO if failed == 0 else logging.WARNING,
            "database_write_batch_summary",
            component="database", operation="aggregate_sql_writes",
            outcome="SUCCESS" if failed == 0 else "PARTIAL_FAILURE",
            details=details,
            duration_ms=round(window_duration, 2),
            failed_count=failed,
        )

    def record_failure(self) -> None:
        with self._lock:
            self._window_failed += 1
            self._total_failed += 1
            self._last_error_at = datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> dict[str, Any]:
        self.flush()
        with self._lock:
            return {
                "successful_statements": self._total_successful,
                "failed_statements": self._total_failed,
                "affected_rows_by_table": dict(self._by_table),
                "last_write_at": self._last_write_at,
                "last_error_at": self._last_error_at,
            }


def instrument_sql_engine(engine: Any) -> SQLWriteObserver:
    """Track SQL mutations without recording SQL text or bound values."""
    from sqlalchemy import event

    observer = SQLWriteObserver()
    engine._blackmarket_write_observer = observer

    def before_cursor_execute(_conn, _cursor, statement, _parameters, context, _executemany):
        match = _WRITE_STATEMENT.match(statement)
        if match and context is not None:
            context._blackmarket_write_started = time.perf_counter()
            context._blackmarket_write_operation = match.group("operation").upper()
            table = _WRITE_TABLE.search(statement)
            context._blackmarket_write_table = table.group("table") if table else "unknown"

    def after_cursor_execute(_conn, _cursor, _statement, _parameters, context, _executemany):
        operation = getattr(context, "_blackmarket_write_operation", None)
        if not operation:
            return
        started = getattr(context, "_blackmarket_write_started", time.perf_counter())
        observer.record_success(
            operation,
            getattr(context, "_blackmarket_write_table", "unknown"),
            (time.perf_counter() - started) * 1000,
            getattr(context, "rowcount", None),
        )

    def handle_error(exception_context):
        context = exception_context.execution_context
        statement = exception_context.statement or ""
        match = _WRITE_STATEMENT.match(statement)
        operation = getattr(context, "_blackmarket_write_operation", None) if context else None
        if not operation and match:
            operation = match.group("operation").upper()
        if not operation:
            return
        observer.record_failure()
        table = _WRITE_TABLE.search(statement)
        started = getattr(context, "_blackmarket_write_started", time.perf_counter()) if context else time.perf_counter()
        log_event(
            logging.getLogger("database.write"),
            logging.ERROR,
            "database_write_failed",
            component="database",
            operation=operation,
            table=getattr(context, "_blackmarket_write_table", table.group("table") if table else "unknown") if context else (table.group("table") if table else "unknown"),
            outcome="FAILURE",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            exception_type=type(exception_context.original_exception).__name__,
            recommendation="Check SQLite availability, schema constraints, and the calling repository operation; no SQL values were logged.",
        )

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine, "handle_error", handle_error)
    return observer
