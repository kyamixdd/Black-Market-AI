"""Public, immutable analysis snapshots and transparent paper challenge rules.

Challenge participation/rankings are intentionally not exposed until the service has
per-user identity and server-owned challenge execution. The existing single shared API
token is not a participant identity and must never be used to award leaderboard scores.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from database.connection import get_session_maker
from database.models import ShareableAnalysisModel

router = APIRouter(prefix="/community", tags=["community"])
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")
TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}


def _json_safe(value: Any, name: str, max_bytes: int = 80_000) -> Any:
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite JSON values") from exc
    if len(raw.encode("utf-8")) > max_bytes:
        raise ValueError(f"{name} exceeds the size limit")
    return value


class ShareAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: str = Field(min_length=2, max_length=20)
    market: str = Field(pattern=r"^(SPOT|FUTURES)$")
    timeframe: str
    analysis_timestamp: datetime
    market_data_source: str = Field(min_length=1, max_length=120)
    data_freshness_seconds: int | None = Field(default=None, ge=0, le=604800)
    indicators: dict[str, Any] = Field(default_factory=dict)
    market_condition: str = Field(default="UNKNOWN", max_length=120)
    supporting_evidence: list[str] = Field(default_factory=list, max_length=30)
    risk_factors: list[str] = Field(default_factory=list, max_length=30)
    strategy_configuration: dict[str, Any] | None = None

    @field_validator("asset")
    @classmethod
    def asset_safe(cls, value: str) -> str:
        value = value.strip().upper()
        if not SYMBOL_RE.fullmatch(value):
            raise ValueError("Asset must be a plain symbol")
        return value

    @field_validator("timeframe")
    @classmethod
    def timeframe_safe(cls, value: str) -> str:
        if value not in TIMEFRAMES:
            raise ValueError("Unsupported timeframe")
        return value

    @field_validator("analysis_timestamp")
    @classmethod
    def timestamp_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("analysis_timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("indicators", "strategy_configuration")
    @classmethod
    def json_fields(cls, value: Any) -> Any:
        if value is not None:
            _json_safe(value, "Analysis fields")
        return value

    @field_validator("supporting_evidence", "risk_factors")
    @classmethod
    def clean_text_lists(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip()[:500] for item in values if item.strip()]
        if len(cleaned) != len(values):
            raise ValueError("Evidence and risk factors must be non-empty strings")
        return cleaned


def _public_payload(request: ShareAnalysisRequest) -> dict[str, Any]:
    # Explicit allowlist: never serialize account/session objects or arbitrary request keys.
    payload = request.model_dump(mode="json")
    payload.pop("strategy_configuration", None) if payload.get("strategy_configuration") is None else None
    payload["disclaimer"] = (
        "Research snapshot only; not investment advice. Markets are risky and "
        "past or simulated performance does not guarantee future results."
    )
    return payload


@router.post("/share/analysis", status_code=201)
def create_shareable_analysis(request: ShareAnalysisRequest):
    """Create an immutable sanitized report; caller must choose what to publish."""
    payload = _public_payload(request)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    share_id = uuid.uuid4().hex
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    maker = get_session_maker()
    with maker() as session:
        session.add(ShareableAnalysisModel(
            share_id=share_id,
            payload_json=serialized,
            content_sha256=digest,
            created_at=datetime.now(timezone.utc),
        ))
        session.commit()
    return {"share_id": share_id, "content_sha256": digest, "report": payload}


@router.get("/share/analysis/{share_id}")
def get_shareable_analysis(share_id: str):
    """Read-only public report endpoint. No account fields are stored or returned."""
    if not re.fullmatch(r"[a-f0-9]{32}", share_id):
        raise HTTPException(status_code=404, detail="Shared analysis not found")
    maker = get_session_maker()
    with maker() as session:
        record = session.scalar(select(ShareableAnalysisModel).where(
            ShareableAnalysisModel.share_id == share_id
        ))
        if record is None:
            raise HTTPException(status_code=404, detail="Shared analysis not found")
        payload = json.loads(record.payload_json)
        return {
            "share_id": record.share_id,
            "content_sha256": record.content_sha256,
            "created_at": record.created_at.isoformat(),
            "report": payload,
        }


CHALLENGES = [
    {
        "challenge_id": "risk-adjusted-performance",
        "name": "Risk-adjusted performance",
        "objective": "Compare simulated return relative to realized volatility and drawdown.",
        "duration_days": 30,
        "starting_capital": 10000,
        "supported_assets": ["BTCUSDT", "ETHUSDT"],
        "trading_rules": "Spot-only, no leverage, positions must be opened and closed through the challenge engine.",
        "fees_and_slippage": {"fee_per_side_pct": 0.1, "slippage_per_side_pct": 0.05},
        "risk_limits": {"max_position_pct": 20, "max_drawdown_pct": 20},
        "ranking": "Composite: 50% risk-adjusted return, 30% drawdown control, 20% rule adherence; profit alone is not ranked.",
    },
    {
        "challenge_id": "drawdown-control",
        "name": "Drawdown control",
        "objective": "Maintain bounded peak-to-trough drawdown while producing positive net return.",
        "duration_days": 30,
        "starting_capital": 10000,
        "supported_assets": ["BTCUSDT", "ETHUSDT"],
        "trading_rules": "Spot-only, no leverage; risk caps enforced server-side.",
        "fees_and_slippage": {"fee_per_side_pct": 0.1, "slippage_per_side_pct": 0.05},
        "risk_limits": {"max_position_pct": 15, "max_drawdown_pct": 10},
        "ranking": "Lowest drawdown among participants meeting minimum trade count; net return is a tie-breaker.",
    },
    {
        "challenge_id": "strategy-consistency",
        "name": "Strategy consistency",
        "objective": "Measure stability of strategy behavior across the challenge period.",
        "duration_days": 30,
        "starting_capital": 10000,
        "supported_assets": ["BTCUSDT", "ETHUSDT"],
        "trading_rules": "Spot-only, no leverage; fixed strategy configuration after start.",
        "fees_and_slippage": {"fee_per_side_pct": 0.1, "slippage_per_side_pct": 0.05},
        "risk_limits": {"max_position_pct": 20, "max_drawdown_pct": 20},
        "ranking": "Consistency score from rolling returns, drawdown, and rule adherence; not raw profit.",
    },
    {
        "challenge_id": "market-regime-research",
        "name": "Market-regime research",
        "objective": "Evaluate strategy robustness across predefined market regimes.",
        "duration_days": 30,
        "starting_capital": 10000,
        "supported_assets": ["BTCUSDT", "ETHUSDT"],
        "trading_rules": "Spot-only, no leverage; regime labels and data windows fixed at challenge start.",
        "fees_and_slippage": {"fee_per_side_pct": 0.1, "slippage_per_side_pct": 0.05},
        "risk_limits": {"max_position_pct": 20, "max_drawdown_pct": 20},
        "ranking": "Average normalized net return across regimes, with drawdown and minimum sample safeguards; raw profit alone is not the ranking metric.",
    },
    {
        "challenge_id": "beginner-strategy-research",
        "name": "Beginner strategy research",
        "objective": "Practice reproducible research using simple supported strategies.",
        "duration_days": 14,
        "starting_capital": 10000,
        "supported_assets": ["BTCUSDT", "ETHUSDT"],
        "trading_rules": "Spot-only, no leverage; use built-in strategies and disclose configuration.",
        "fees_and_slippage": {"fee_per_side_pct": 0.1, "slippage_per_side_pct": 0.05},
        "risk_limits": {"max_position_pct": 10, "max_drawdown_pct": 10},
        "ranking": "Research completeness and rule adherence first; risk-adjusted net return and risk metrics second; raw profit alone is not the ranking metric.",
    },
]


@router.get("/challenges")
def list_paper_challenges():
    """Return documented challenge specifications; no client-submitted scores."""
    return {"challenges": CHALLENGES, "participation_enabled": False,
            "reason": "Server-owned challenge accounts and participant identity are not yet available."}


@router.get("/challenges/{challenge_id}")
def get_paper_challenge(challenge_id: str):
    for challenge in CHALLENGES:
        if challenge["challenge_id"] == challenge_id:
            return {**challenge, "participation_enabled": False}
    raise HTTPException(status_code=404, detail="Challenge not found")
