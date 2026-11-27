"""Frontend diagnostic event ingestion."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.observability import log_event, redact_sensitive_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class FrontendDiagnosticEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    timestamp: datetime
    level: Literal["INFO", "WARNING", "ERROR"]
    event: str = Field(min_length=1, max_length=120)
    operation: str = Field(min_length=1, max_length=160)
    status: Literal["SUCCESS", "FAILURE", "WARNING"]
    duration_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    endpoint: str | None = Field(default=None, max_length=200)
    status_code: int | None = Field(default=None, ge=100, le=599)
    detail: str | None = Field(default=None, max_length=300)
    recommendation: str | None = Field(default=None, max_length=300)

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_path_only(cls, value: str | None) -> str | None:
        if value is not None and (not value.startswith("/") or "?" in value or "#" in value):
            raise ValueError("endpoint must be a path without query or fragment")
        return value

    @field_validator("event", "operation", "endpoint", "detail", "recommendation")
    @classmethod
    def redact_diagnostic_text(cls, value: str | None) -> str | None:
        return redact_sensitive_text(value) if value is not None else None


class FrontendDiagnosticBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[FrontendDiagnosticEvent] = Field(min_length=1, max_length=50)


@router.post("/frontend")
async def ingest_frontend_diagnostics(batch: FrontendDiagnosticBatch):
    for item in batch.events:
        level = {
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }[item.level]
        log_event(
            logger,
            level,
            "frontend_diagnostic",
            component="frontend",
            operation=item.operation,
            phase=item.event,
            outcome=item.status,
            duration_ms=item.duration_ms,
            endpoint=item.endpoint,
            status_code=item.status_code,
            details=item.detail,
            recommendation=item.recommendation,
            frontend_event_id=item.id,
        )
    return {"accepted": len(batch.events)}
