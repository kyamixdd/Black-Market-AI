"""Structured, redacted application logging helpers."""
from __future__ import annotations

import json
import logging
import re
import time
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
        for key in ("event", "request_id", "method", "path", "status_code", "duration_ms", "component", "operation"):
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
        if key not in {"token", "password", "secret", "authorization", "api_key"}
    }
    logger.log(level, event, extra={"event": event, **safe_fields})
