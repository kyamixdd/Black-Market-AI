"""Persistent strategy definitions, backtest reports, and workspaces."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from database.connection import get_session_maker
from database.repositories import Repository

router = APIRouter(prefix="/research", tags=["research"])
_OWNER_KEY = "local"
_SUPPORTED_STRATEGIES = {"momentum", "breakout", "trend_following", "mean_reversion", "reversal"}


def _repo() -> Repository:
    return Repository(get_session_maker())


def _check_json_size(value: Any, label: str, max_bytes: int = 250_000) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{label} must be valid JSON data") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{label} exceeds the {max_bytes}-byte limit")
    return value


class StrategyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    strategy_key: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    definition: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=30)
    version: int = Field(default=1, ge=1, le=100000)

    @field_validator("strategy_key")
    @classmethod
    def supported_strategy(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in _SUPPORTED_STRATEGIES:
            raise ValueError("strategy_key must be a supported built-in strategy")
        return value

    @field_validator("definition", "tags")
    @classmethod
    def bounded_json(cls, value: Any) -> Any:
        return _check_json_size(value, "strategy definition")


class WorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = Field(default=1, ge=1, le=1000)

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _check_json_size(value, "workspace payload", 500_000)


class ReportRequest(BaseModel):
    strategy_id: str | None = Field(default=None, max_length=64)
    strategy_name: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$")
    market: str = Field(pattern=r"^(SPOT|FUTURES)$")
    timeframe: str = Field(pattern=r"^(1m|3m|5m|15m|30m|1h|4h|1d|1w)$")
    status: str = Field(default="saved", max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config", "report")
    @classmethod
    def bounded_report_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _check_json_size(value, "backtest report", 1_000_000)


@router.get("/strategies")
def list_saved_strategies():
    return {"strategies": _repo().list_strategy_definitions()}


@router.post("/strategies")
def save_strategy(request: StrategyRequest):
    return _repo().save_strategy_definition({
        "strategy_id": uuid.uuid4().hex,
        **request.model_dump(),
    })


@router.get("/strategies/{strategy_id}")
def get_saved_strategy(strategy_id: str):
    if not re.fullmatch(r"[a-fA-F0-9-]{8,64}", strategy_id):
        raise HTTPException(status_code=422, detail="Invalid strategy identifier")
    result = _repo().get_strategy_definition(strategy_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Saved strategy not found")
    return result


@router.put("/strategies/{strategy_id}")
def update_saved_strategy(strategy_id: str, request: StrategyRequest):
    if not re.fullmatch(r"[a-fA-F0-9-]{8,64}", strategy_id):
        raise HTTPException(status_code=422, detail="Invalid strategy identifier")
    repository = _repo()
    existing = repository.get_strategy_definition(strategy_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Saved strategy not found")
    return repository.save_strategy_definition({
        "strategy_id": strategy_id, **request.model_dump(),
        "version": max(existing["version"] + 1, request.version),
    })


@router.delete("/strategies/{strategy_id}")
def delete_saved_strategy(strategy_id: str):
    if not _repo().delete_strategy_definition(strategy_id):
        raise HTTPException(status_code=404, detail="Saved strategy not found")
    return {"status": "deleted", "strategy_id": strategy_id}


@router.get("/reports")
def list_backtest_reports():
    return {"reports": _repo().list_backtest_reports()}


@router.post("/reports")
def save_backtest_report(request: ReportRequest):
    return _repo().save_backtest_report({
        "report_id": uuid.uuid4().hex, **request.model_dump(),
    })


@router.get("/reports/{report_id}")
def get_backtest_report(report_id: str):
    if not re.fullmatch(r"[a-fA-F0-9-]{8,64}", report_id):
        raise HTTPException(status_code=422, detail="Invalid report identifier")
    result = _repo().get_backtest_report(report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest report not found")
    return result


@router.delete("/reports/{report_id}")
def delete_backtest_report(report_id: str):
    if not _repo().delete_backtest_report(report_id):
        raise HTTPException(status_code=404, detail="Backtest report not found")
    return {"status": "deleted", "report_id": report_id}


@router.get("/workspaces")
def list_workspaces():
    return {"workspaces": _repo().list_workspaces(_OWNER_KEY)}


@router.post("/workspaces")
def save_workspace(request: WorkspaceRequest):
    return _repo().save_workspace({
        "workspace_id": uuid.uuid4().hex, "owner_key": _OWNER_KEY,
        **request.model_dump(),
    })


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: str):
    if not re.fullmatch(r"[a-fA-F0-9-]{8,64}", workspace_id):
        raise HTTPException(status_code=422, detail="Invalid workspace identifier")
    result = _repo().get_workspace(workspace_id, _OWNER_KEY)
    if result is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return result


@router.put("/workspaces/{workspace_id}")
def update_workspace(workspace_id: str, request: WorkspaceRequest):
    if not re.fullmatch(r"[a-fA-F0-9-]{8,64}", workspace_id):
        raise HTTPException(status_code=422, detail="Invalid workspace identifier")
    repository = _repo()
    existing = repository.get_workspace(workspace_id, _OWNER_KEY)
    if existing is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return repository.save_workspace({
        "workspace_id": workspace_id, "owner_key": _OWNER_KEY,
        **request.model_dump(),
    })


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str):
    if not _repo().delete_workspace(workspace_id, _OWNER_KEY):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"status": "deleted", "workspace_id": workspace_id}
