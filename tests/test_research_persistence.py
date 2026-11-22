"""Stage 10 research persistence API and automatic report tests."""
from database.connection import Database
from database.repositories import Repository
from src_tauri.backend.api.routes import learning, research


def test_strategy_lab_report_helper_persists_completed_result(monkeypatch, tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'auto-report.db'}")
    db.init_db()
    monkeypatch.setattr(learning, "get_session_maker", db.session_maker)
    report_id = learning._save_lab_report(
        "momentum",
        {
            "symbol": "BTCUSDT", "market": "SPOT", "timeframe": "1h",
            "start_date": "2026-01-01T00:00:00Z", "end_date": "2026-02-01T00:00:00Z",
            "initial_capital": 1000,
        },
        {"status": "completed", "metrics": {"net_return_pct": 4.5}, "trades": []},
    )
    report = Repository(db.session_maker()).get_backtest_report(report_id)
    assert report is not None
    assert report["strategy_name"] == "momentum"
    assert report["report"]["metrics"]["net_return_pct"] == 4.5
    assert report["config"]["initial_capital"] == 1000
    db.close()


def test_research_api_create_and_restore_workspace(monkeypatch, tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'api-workspace.db'}")
    db.init_db()
    monkeypatch.setattr(research, "get_session_maker", db.session_maker)
    saved = research.save_workspace(research.WorkspaceRequest(
        name="Desktop research", payload={"screen": "Strategy Lab", "marketType": "SPOT"},
    ))
    restored = research.get_workspace(saved["workspace_id"])
    assert restored["payload"]["screen"] == "Strategy Lab"
    assert research.delete_workspace(saved["workspace_id"])["status"] == "deleted"
    db.close()



def test_research_api_strategy_and_report_crud(monkeypatch, tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'api-research.db'}")
    db.init_db()
    monkeypatch.setattr(research, "get_session_maker", db.session_maker)

    strategy = research.save_strategy(research.StrategyRequest(
        name="My breakout", strategy_key="breakout",
        definition={"min_score": 3, "risk_per_trade_pct": 1},
        tags=["saved"],
    ))
    assert strategy["version"] == 1
    updated = research.update_saved_strategy(strategy["strategy_id"], research.StrategyRequest(
        name="My breakout v2", strategy_key="breakout",
        definition={"min_score": 4},
    ))
    assert updated["version"] == 2
    assert research.get_saved_strategy(strategy["strategy_id"])["name"] == "My breakout v2"

    report = research.save_backtest_report(research.ReportRequest(
        strategy_id=strategy["strategy_id"], strategy_name="breakout",
        symbol="ETHUSDT", market="SPOT", timeframe="15m",
        config={"capital": 500}, report={"status": "evaluated", "trades": []},
    ))
    assert research.get_backtest_report(report["report_id"])["config"]["capital"] == 500
    assert research.delete_backtest_report(report["report_id"])["status"] == "deleted"
    assert research.delete_saved_strategy(strategy["strategy_id"])["status"] == "deleted"
    db.close()

def test_research_api_rejects_unsupported_strategy_key():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        research.StrategyRequest(name="Arbitrary", strategy_key="python", definition={"code": "exec()"})
