"""Public community strategy library; private trading data is never queried here."""
from __future__ import annotations

import json
import hmac
import hashlib
import re
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.repositories import Repository
from database.connection import get_session_maker
from config import SUPPORTED_TIMEFRAMES

router = APIRouter(prefix="/community", tags=["community"])
SUPPORTED = {"momentum", "breakout", "trend_following", "mean_reversion", "reversal"}
TIMEFRAMES = set(SUPPORTED_TIMEFRAMES)
OWNER_PATTERN = re.compile(r"^[a-fA-F0-9-]{36}$")


def _repo() -> Repository:
    return Repository(get_session_maker())


def _owner(request: Request, value: str | None) -> str:
    if not value or not OWNER_PATTERN.fullmatch(value):
        raise HTTPException(status_code=401, detail="Community identity is unavailable. Sign in again.")
    principal = getattr(request.state, "authenticated_principal", None)
    if not isinstance(principal, str) or not principal:
        raise HTTPException(status_code=401, detail="Authenticated community identity is unavailable.")
    authenticated_owner = hmac.new(
        principal.encode("ascii"), value.lower().encode("ascii"), hashlib.sha256,
    ).hexdigest()
    _repo().bind_community_owner(value, authenticated_owner)
    return authenticated_owner


def _validate_public_id(public_id: str) -> str:
    if not re.fullmatch(r"[a-fA-F0-9]{32}", public_id):
        raise HTTPException(status_code=422, detail="Invalid strategy identifier")
    return public_id


def _reject_private_fields(value: Any, path: str = "rules") -> Any:
    forbidden_fragments = ("apikey", "secret", "credential", "private", "tradehistory",
                          "personalsettings", "accountbalance", "walletbalance", "accesstoken")
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if any(fragment in normalized for fragment in forbidden_fragments):
                raise ValueError(f"{path} contains a private field name: {key}")
            _reject_private_fields(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_private_fields(nested, f"{path}[{index}]")
    return value


def _valid_json(value: Any, label: str, limit: int = 100_000):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be valid finite JSON") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{label} exceeds size limit")
    return value


class ReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_trades: int | None = Field(default=None, ge=0, le=1_000_000)
    win_rate_pct: float | None = Field(default=None, ge=0, le=100)
    net_return_pct: float | None = Field(default=None, ge=-100_000, le=100_000)
    max_drawdown_pct: float | None = Field(default=None, ge=0, le=100_000)
    profit_factor: float | None = Field(default=None, ge=0, le=1_000_000)
    sample_period: str = Field(default="", max_length=120)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    strategy_key: str = Field(min_length=1, max_length=64)
    rules: dict[str, Any] = Field(min_length=1)
    supported_assets: list[str] = Field(default_factory=list, max_length=50)
    supported_timeframes: list[str] = Field(default_factory=list, min_length=1, max_length=12)
    risk_configuration: dict[str, float] = Field(default_factory=dict)
    known_limitations: list[str] = Field(default_factory=list, max_length=30)
    backtest_report: ReportSummary = Field(default_factory=ReportSummary)
    source_report_id: str | None = Field(default=None, max_length=64)

    @field_validator("source_report_id")
    @classmethod
    def report_id_safe(cls, value):
        if value is not None and not re.fullmatch(r"[a-fA-F0-9-]{8,64}", value):
            raise ValueError("Invalid saved backtest report identifier.")
        return value

    @field_validator("strategy_key")
    @classmethod
    def strategy_supported(cls, value: str):
        value = value.strip().lower()
        if value not in SUPPORTED:
            raise ValueError("Choose a supported built-in strategy.")
        return value

    @field_validator("rules")
    @classmethod
    def rules_safe(cls, value):
        _valid_json(value, "Strategy rules", 100_000)
        return _reject_private_fields(value)

    @field_validator("supported_assets")
    @classmethod
    def assets_safe(cls, values):
        clean = []
        for value in values:
            symbol = value.strip().upper()
            if not re.fullmatch(r"[A-Z0-9]{2,20}", symbol):
                raise ValueError("Asset symbols must be plain exchange symbols.")
            if symbol not in clean:
                clean.append(symbol)
        return clean

    @field_validator("supported_timeframes")
    @classmethod
    def timeframes_safe(cls, values):
        if any(value not in TIMEFRAMES for value in values):
            raise ValueError("Unsupported timeframe.")
        return list(dict.fromkeys(values))

    @field_validator("risk_configuration")
    @classmethod
    def risk_safe(cls, value):
        allowed = {"risk_per_trade_pct", "max_position_pct", "stop_loss_pct", "take_profit_pct", "max_open_positions", "leverage"}
        if set(value) - allowed:
            raise ValueError("Risk configuration contains unsupported fields.")
        if any(not isinstance(v, (int, float)) or not (0 <= v <= 100_000) for v in value.values()):
            raise ValueError("Risk values must be finite non-negative numbers.")
        return _valid_json(value, "Risk configuration", 10_000)

    @field_validator("known_limitations")
    @classmethod
    def limitations_safe(cls, values):
        return [str(v).strip()[:500] for v in values if str(v).strip()]


def _report_for_publication(request: PublishRequest) -> tuple[dict[str, Any], str, str | None]:
    if not request.source_report_id:
        return request.backtest_report.model_dump(exclude_none=True), "USER_SUBMITTED", None
    saved = _repo().get_backtest_report(request.source_report_id)
    if saved is None or saved.get("origin") != "LOCAL_BACKTEST":
        raise HTTPException(status_code=422, detail="Only a locally generated Strategy Lab report can be referenced as a local backtest.")
    if str(saved.get("status", "")).lower() not in {"completed", "ok"}:
        raise HTTPException(status_code=422, detail="The referenced backtest is not completed.")
    result = saved.get("report") or {}
    metrics = result.get("metrics") if isinstance(result, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}
    trades = result.get("trades") if isinstance(result, dict) else []
    config = saved.get("config") or {}
    start = str(config.get("start_date") or "")
    end = str(config.get("end_date") or "")
    sample_period = f"{start[:10]} to {end[:10]}" if start and end else ""
    pf = metrics.get("profit_factor")
    if not isinstance(pf, (int, float)) or not 0 <= float(pf) <= 1_000_000:
        pf = None
    summary = ReportSummary(
        total_trades=metrics.get("trade_count", len(trades) if isinstance(trades, list) else None),
        win_rate_pct=metrics.get("win_rate_pct"),
        net_return_pct=metrics.get("net_return_pct"),
        max_drawdown_pct=metrics.get("max_drawdown_pct"),
        profit_factor=pf,
        sample_period=sample_period,
    )
    return summary.model_dump(exclude_none=True), "LOCAL_BACKTEST", request.source_report_id


class FavoriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: bool


class ReportFlagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["misleading_results", "spam", "abusive", "copyright", "other"]
    details: str = Field(default="", max_length=1000)


@router.get("/strategies")
def search_public_strategies(
    request: Request,
    q: str = Query(default="", max_length=120),
    strategy_key: str = Query(default="", max_length=64),
    asset: str = Query(default="", max_length=20),
    timeframe: str = Query(default="", max_length=8),
    sort: Literal["recent", "updated", "name"] = "recent",
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner"),
):
    owner = (
        _owner(request, x_bm_community_owner)
        if OWNER_PATTERN.fullmatch(x_bm_community_owner or "")
        else None
    )
    return {"strategies": _repo().list_public_strategies(query=q, strategy_key=strategy_key.lower(),
        asset=asset.upper(), timeframe=timeframe, sort=sort, owner_key=owner, limit=limit, offset=offset)}


@router.get("/favorites")
def favorites(request: Request, x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner")):
    return {"strategies": _repo().list_strategy_favorites(_owner(request, x_bm_community_owner))}


@router.post("/strategies")
def publish_strategy(http_request: Request, payload: PublishRequest,
                     x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner")):
    owner = _owner(http_request, x_bm_community_owner)
    record = payload.model_dump()
    record["public_id"] = uuid.uuid4().hex
    record["backtest_report"], record["report_provenance"], record["source_report_id"] = _report_for_publication(payload)
    try:
        return _repo().publish_public_strategy(record, owner)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/strategies/{public_id}")
def strategy_details(public_id: str, request: Request,
                     x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner")):
    _validate_public_id(public_id)
    owner = (
        _owner(request, x_bm_community_owner)
        if OWNER_PATTERN.fullmatch(x_bm_community_owner or "")
        else None
    )
    result = _repo().get_public_strategy(public_id, owner)
    if result is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return result


@router.put("/strategies/{public_id}")
def update_strategy(public_id: str, http_request: Request, payload: PublishRequest,
                    x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner")):
    _validate_public_id(public_id)
    owner = _owner(http_request, x_bm_community_owner)
    existing = _repo().get_public_strategy(public_id, owner)
    if existing is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    record = payload.model_dump()
    record["public_id"] = public_id
    record["backtest_report"], record["report_provenance"], record["source_report_id"] = _report_for_publication(payload)
    try:
        return _repo().publish_public_strategy(record, owner)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/strategies/{public_id}")
def unpublish_strategy(public_id: str, request: Request,
                       x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner")):
    _validate_public_id(public_id)
    if not _repo().hide_public_strategy(public_id, _owner(request, x_bm_community_owner)):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "unpublished"}


@router.post("/strategies/{public_id}/favorite")
def favorite_strategy(public_id: str, http_request: Request, payload: FavoriteRequest,
                     x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner")):
    _validate_public_id(public_id)
    if not _repo().set_strategy_favorite(public_id, _owner(http_request, x_bm_community_owner), payload.favorite):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "updated", "favorite": payload.favorite}


@router.post("/strategies/{public_id}/report")
def report_strategy(public_id: str, http_request: Request, payload: ReportFlagRequest,
                   x_bm_community_owner: str | None = Header(default=None, alias="X-BM-Community-Owner")):
    _validate_public_id(public_id)
    if not _repo().flag_public_strategy(public_id, _owner(http_request, x_bm_community_owner), payload.reason, payload.details):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "submitted"}
