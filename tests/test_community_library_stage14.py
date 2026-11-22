"""Stage 14 public strategy library authorization, privacy and provenance tests."""
import hashlib
import json
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from database.connection import Database
from database.repositories import Repository
from src_tauri.backend.api.routes import community, learning


def owner():
    return str(uuid.uuid4())


def payload(name="Public Momentum"):
    return community.PublishRequest(
        name=name,
        description="A community-shared ruleset.",
        strategy_key="momentum",
        rules={"entry": "momentum threshold", "exit": "ATR stop"},
        supported_assets=["BTCUSDT", "ETHUSDT"],
        supported_timeframes=["15m", "1h"],
        risk_configuration={"risk_per_trade_pct": 1.0, "max_position_pct": 10.0},
        known_limitations=["User-submitted report; not a profit forecast."],
        backtest_report=community.ReportSummary(total_trades=80, win_rate_pct=54.0,
            net_return_pct=7.5, max_drawdown_pct=4.0, sample_period="2025-01"),
    )


def setup_db(monkeypatch, tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'community.db'}")
    db.init_db()
    monkeypatch.setattr(community, "get_session_maker", db.session_maker)
    return db, Repository(db.session_maker())


def test_publish_public_strategy_and_report_provenance(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a = owner()
    published = community.publish_strategy(payload(), a)
    assert published["report_provenance"] == "USER_SUBMITTED"
    assert published["version"] == 1
    assert published["supported_assets"] == ["BTCUSDT", "ETHUSDT"]
    report_json = json.dumps(payload().backtest_report.model_dump(exclude_none=True),
        ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert published["report_sha256"] == hashlib.sha256(report_json.encode()).hexdigest()
    assert len(repo.list_public_strategies()) == 1
    db.close()


def test_owner_can_update_version_and_history_is_immutable(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a = owner()
    published = community.publish_strategy(payload(), a)
    updated = community.update_strategy(published["public_id"], payload("Momentum v2"), a)
    details = repo.get_public_strategy(published["public_id"], a)
    assert updated["version"] == 2
    assert [v["version"] for v in details["version_history"]] == [2, 1]
    assert details["version_history"][1]["snapshot"]["name"] == "Public Momentum"
    db.close()


def test_other_owner_cannot_update_or_unpublish(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a, b = owner(), owner()
    published = community.publish_strategy(payload(), a)
    with pytest.raises(HTTPException):
        community.update_strategy(published["public_id"], payload("Hijack"), b)
    with pytest.raises(HTTPException):
        community.unpublish_strategy(published["public_id"], b)
    assert repo.get_public_strategy(published["public_id"])["name"] == "Public Momentum"
    db.close()


def test_private_strategy_not_listed_after_unpublish(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a = owner()
    published = community.publish_strategy(payload(), a)
    community.unpublish_strategy(published["public_id"], a)
    assert repo.list_public_strategies() == []
    assert repo.get_public_strategy(published["public_id"], a)["name"] == "Public Momentum"
    assert repo.get_public_strategy(published["public_id"], owner()) is None
    db.close()


def test_favorites_search_and_content_report(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a, b = owner(), owner()
    published = community.publish_strategy(payload(), a)
    assert repo.list_public_strategies(query="momentum")[0]["name"] == "Public Momentum"
    assert community.favorite_strategy(published["public_id"], community.FavoriteRequest(favorite=True), b)["favorite"]
    assert repo.list_public_strategies(owner_key=b)[0]["is_favorite"]
    assert community.report_strategy(published["public_id"],
        community.ReportFlagRequest(reason="misleading_results", details="Please review provenance."), b)["status"] == "submitted"
    db.close()


def test_invalid_strategy_and_risk_fields_are_rejected():
    with pytest.raises(ValidationError):
        community.PublishRequest(name="Invalid", strategy_key="arbitrary python",
            rules={"entry": "x"}, supported_timeframes=["15m"])
    with pytest.raises(ValidationError):
        community.PublishRequest(name="Bad", strategy_key="momentum",
            rules={"code": "not executable"}, risk_configuration={"account_balance": 999999},
            supported_timeframes=["15m"])
    with pytest.raises(ValidationError):
        community.PublishRequest(name="Leak", strategy_key="momentum",
            rules={"api_key": "secret"}, supported_timeframes=["15m"])


def test_public_record_contains_no_account_or_trade_history_fields(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    published = community.publish_strategy(payload(), owner())
    public = repo.get_public_strategy(published["public_id"])
    forbidden = {"account_balance", "api_key", "api_secret", "private_trade_history", "personal_settings", "owner_key"}
    assert not (forbidden & set(public))
    assert "trade_history" not in json.dumps(public).lower()
    db.close()

def test_local_backtest_report_is_distinguished_and_summary_is_server_derived(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    monkeypatch.setattr(learning, "get_session_maker", db.session_maker)
    report_id = learning._save_lab_report(
        "momentum",
        {"symbol": "BTCUSDT", "market": "SPOT", "timeframe": "15m",
         "start_date": "2026-01-01T00:00:00Z", "end_date": "2026-02-01T00:00:00Z"},
        {"status": "completed", "metrics": {"trade_count": 12, "win_rate_pct": 58.0,
         "net_return_pct": 3.2, "max_drawdown_pct": 2.1, "profit_factor": 1.4}, "trades": []},
    )
    request = community.PublishRequest(name="Local result", strategy_key="momentum",
        rules={"entry": "documented"}, supported_timeframes=["15m"], source_report_id=report_id)
    published = community.publish_strategy(request, owner())
    assert published["report_provenance"] == "LOCAL_BACKTEST"
    assert published["source_report_id"] == report_id
    assert published["backtest_report"]["total_trades"] == 12
    assert published["backtest_report"]["win_rate_pct"] == 58.0
    assert published["verification_status"] == "NOT_VERIFIED"
    assert published["reproducibility_status"] == "NOT_REPLAYED"
    db.close()


def test_user_saved_report_cannot_claim_application_generated_provenance(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    user_report = repo.save_backtest_report({
        "report_id": uuid.uuid4().hex, "strategy_name": "momentum", "symbol": "BTCUSDT",
        "market": "SPOT", "timeframe": "15m", "status": "completed",
        "config": {}, "report": {"metrics": {"win_rate_pct": 99}},
    })
    assert user_report["origin"] == "USER_SUBMITTED"
    request = community.PublishRequest(name="Submitted", strategy_key="momentum",
        rules={"entry": "provided"}, supported_timeframes=["15m"],
        source_report_id=user_report["report_id"])
    with pytest.raises(HTTPException):
        community.publish_strategy(request, owner())
    db.close()

