"""Stage 14 public strategy library authorization, privacy and provenance tests."""
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from database.connection import Database
from database.repositories import Repository
from src_tauri.backend.api.routes import community, learning


def owner():
    return str(uuid.uuid4())


def authenticated_request(principal="desktop-token"):
    request = Request({
        "type": "http", "method": "POST", "path": "/api/community/strategies",
        "headers": [], "query_string": b"", "server": ("test", 80),
        "client": ("127.0.0.1", 1234), "scheme": "http",
        "http_version": "1.1", "root_path": "",
    })
    request.state.authenticated_principal = hashlib.sha256(principal.encode()).hexdigest()
    return request


def bound_owner(identity, principal="desktop-token"):
    principal_key = hashlib.sha256(principal.encode()).hexdigest()
    return hmac.new(
        principal_key.encode(), identity.lower().encode(), hashlib.sha256,
    ).hexdigest()


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
    auth = authenticated_request()
    published = community.publish_strategy(auth, payload(), a)
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
    auth = authenticated_request()
    published = community.publish_strategy(auth, payload(), a)
    updated = community.update_strategy(published["public_id"], auth, payload("Momentum v2"), a)
    details = repo.get_public_strategy(published["public_id"], bound_owner(a))
    assert updated["version"] == 2
    assert [v["version"] for v in details["version_history"]] == [2, 1]
    assert details["version_history"][1]["snapshot"]["name"] == "Public Momentum"
    db.close()


def test_other_owner_cannot_update_or_unpublish(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a, b = owner(), owner()
    auth_a, auth_b = authenticated_request("principal-a"), authenticated_request("principal-b")
    published = community.publish_strategy(auth_a, payload(), a)
    with pytest.raises(HTTPException):
        community.update_strategy(published["public_id"], auth_b, payload("Hijack"), a)
    with pytest.raises(HTTPException):
        community.unpublish_strategy(published["public_id"], auth_b, a)
    assert repo.get_public_strategy(published["public_id"])["name"] == "Public Momentum"
    db.close()


def test_private_strategy_not_listed_after_unpublish(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a = owner()
    auth = authenticated_request()
    published = community.publish_strategy(auth, payload(), a)
    community.unpublish_strategy(published["public_id"], auth, a)
    assert repo.list_public_strategies() == []
    assert repo.get_public_strategy(published["public_id"], bound_owner(a))["name"] == "Public Momentum"
    assert repo.get_public_strategy(published["public_id"], bound_owner(owner())) is None
    db.close()


def test_favorites_search_and_content_report(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    a, b = owner(), owner()
    auth = authenticated_request()
    published = community.publish_strategy(auth, payload(), a)
    assert repo.list_public_strategies(query="momentum")[0]["name"] == "Public Momentum"
    assert community.favorite_strategy(
        published["public_id"], auth, community.FavoriteRequest(favorite=True), b,
    )["favorite"]
    assert repo.list_public_strategies(owner_key=bound_owner(b))[0]["is_favorite"]
    assert community.report_strategy(
        published["public_id"], auth,
        community.ReportFlagRequest(reason="misleading_results", details="Please review provenance."),
        b,
    )["status"] == "submitted"
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
    published = community.publish_strategy(authenticated_request(), payload(), owner())
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
    published = community.publish_strategy(authenticated_request(), request, owner())
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
        community.publish_strategy(authenticated_request(), request, owner())
    db.close()


def test_community_identity_is_bound_to_authenticated_principal():
    identity = owner()
    first = bound_owner(identity, "principal-a")
    second = bound_owner(identity, "principal-b")
    assert first != second
    with pytest.raises(HTTPException) as error:
        community._owner(authenticated_request_without_principal(), identity)
    assert error.value.status_code == 401


def test_legacy_community_owner_is_migrated_when_authenticated(monkeypatch, tmp_path):
    db, repo = setup_db(monkeypatch, tmp_path)
    identity = owner()
    record = payload().model_dump()
    record["public_id"] = uuid.uuid4().hex
    repo.publish_public_strategy(record, identity)

    authenticated_owner = community._owner(authenticated_request(), identity)

    migrated = repo.get_public_strategy(record["public_id"], authenticated_owner)
    assert migrated is not None
    assert migrated["is_owner"] is True
    db.close()


def test_community_mutations_reject_malformed_public_ids():
    request = authenticated_request()
    invalid_id = "../not-an-id"
    with pytest.raises(HTTPException) as error:
        community.update_strategy(invalid_id, request, payload(), owner())
    assert error.value.status_code == 422
    with pytest.raises(HTTPException):
        community.unpublish_strategy(invalid_id, request, owner())
    with pytest.raises(HTTPException):
        community.favorite_strategy(
            invalid_id, request, community.FavoriteRequest(favorite=True), owner(),
        )
    with pytest.raises(HTTPException):
        community.report_strategy(
            invalid_id, request,
            community.ReportFlagRequest(reason="spam"), owner(),
        )


def authenticated_request_without_principal():
    return Request({
        "type": "http", "method": "POST", "path": "/api/community/strategies",
        "headers": [], "query_string": b"", "server": ("test", 80),
        "client": ("127.0.0.1", 1234), "scheme": "http",
        "http_version": "1.1", "root_path": "",
    })

