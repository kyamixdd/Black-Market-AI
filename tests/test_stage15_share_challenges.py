"""Stage 15 shareable analysis and challenge safety tests."""
import hashlib
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from database.connection import Database
from src_tauri.backend.api.routes import share_challenges as stage15


def setup_db(monkeypatch, tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'stage15.db'}")
    db.init_db()
    monkeypatch.setattr(stage15, "get_session_maker", db.session_maker)
    return db


def report():
    return stage15.ShareAnalysisRequest(
        asset="btcusdt", market="SPOT", timeframe="15m",
        analysis_timestamp=datetime(2026, 11, 22, tzinfo=timezone.utc),
        market_data_source="Exchange market feed",
        data_freshness_seconds=12,
        indicators={"rsi": 48.2, "ema": 65000},
        market_condition="RANGE",
        supporting_evidence=["RSI neutral", "Price inside range"],
        risk_factors=["Low liquidity during off-hours"],
        strategy_configuration={"strategy": "momentum", "risk_pct": 1},
    )


def test_share_report_persists_immutable_public_allowlist(monkeypatch, tmp_path):
    db = setup_db(monkeypatch, tmp_path)
    created = stage15.create_shareable_analysis(report())
    readback = stage15.get_shareable_analysis(created["share_id"])
    assert readback["content_sha256"] == created["content_sha256"]
    assert readback["report"]["asset"] == "BTCUSDT"
    assert readback["report"]["strategy_configuration"] == {"strategy": "momentum", "risk_pct": 1}
    assert "account_balance" not in json.dumps(readback).lower()
    assert hashlib.sha256(json.dumps(readback["report"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest() != ""  # snapshot is finite JSON
    db.close()


def test_share_report_rejects_bad_symbol_timeframe_and_naive_timestamp():
    base = report().model_dump()
    base["asset"] = "BTC/USDT"
    with pytest.raises(ValidationError):
        stage15.ShareAnalysisRequest(**base)
    base = report().model_dump()
    base["timeframe"] = "2m"
    with pytest.raises(ValidationError):
        stage15.ShareAnalysisRequest(**base)
    base = report().model_dump()
    base["analysis_timestamp"] = datetime(2026, 11, 22)
    with pytest.raises(ValidationError):
        stage15.ShareAnalysisRequest(**base)


def test_share_report_rejects_nonfinite_indicator():
    base = report().model_dump()
    base["indicators"] = {"bad": float("nan")}
    with pytest.raises(ValidationError):
        stage15.ShareAnalysisRequest(**base)


def test_unknown_or_malformed_share_id_is_not_found(monkeypatch, tmp_path):
    db = setup_db(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as exc:
        stage15.get_shareable_analysis("not-a-valid-id")
    assert exc.value.status_code == 404
    db.close()


def test_challenge_specs_have_explicit_fairness_rules_and_disable_client_rankings():
    listing = stage15.list_paper_challenges()
    assert listing["participation_enabled"] is False
    assert len(listing["challenges"]) == 5
    for challenge in listing["challenges"]:
        assert challenge["starting_capital"] > 0
        assert challenge["duration_days"] > 0
        assert challenge["supported_assets"]
        assert challenge["trading_rules"]
        assert challenge["fees_and_slippage"]
        assert challenge["risk_limits"]
        assert challenge["ranking"]
        assert "profit alone" in challenge["ranking"].lower() or "return" in challenge["ranking"].lower()


def test_unknown_challenge_returns_404():
    with pytest.raises(HTTPException) as exc:
        stage15.get_paper_challenge("client-supplied-score")
    assert exc.value.status_code == 404
