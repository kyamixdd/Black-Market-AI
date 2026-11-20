"""Runtime settings validation and atomic persistence tests."""
import json

import pytest
from pydantic import ValidationError

from core import runtime_settings_store
from src_tauri.backend.api.routes.schemas import SettingsRequest


def test_settings_reject_unsupported_timeframe():
    with pytest.raises(ValidationError):
        SettingsRequest(timeframes=["15m", "2m"])


def test_settings_reject_empty_or_duplicate_timeframes():
    with pytest.raises(ValidationError):
        SettingsRequest(timeframes=[])
    with pytest.raises(ValidationError):
        SettingsRequest(timeframes=["15m", "15m"])


def test_settings_reject_out_of_range_risk_and_capital():
    with pytest.raises(ValidationError):
        SettingsRequest(risk_per_trade_pct=8)
    with pytest.raises(ValidationError):
        SettingsRequest(spot_initial_balance=0)
    with pytest.raises(ValidationError):
        SettingsRequest(max_futures_positions=0)


def test_settings_reject_unknown_fields():
    with pytest.raises(ValidationError):
        SettingsRequest(api_secret="must-not-be-stored")


def test_runtime_settings_store_atomic_round_trip(tmp_path, monkeypatch):
    target = tmp_path / "private" / "runtime_settings.json"
    monkeypatch.setattr(runtime_settings_store, "SETTINGS_PATH", target)
    settings = {"risk_per_trade_pct": 0.5, "timeframes": ["15m", "1h"]}
    runtime_settings_store.save_runtime_settings(settings)
    assert runtime_settings_store.load_runtime_settings() == settings
    assert json.loads(target.read_text(encoding="utf-8")) == settings
    assert not list(target.parent.glob(".runtime-settings-*.tmp"))


def test_runtime_settings_store_rejects_corrupt_json(tmp_path, monkeypatch):
    target = tmp_path / "runtime_settings.json"
    target.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(runtime_settings_store, "SETTINGS_PATH", target)
    with pytest.raises(RuntimeError):
        runtime_settings_store.load_runtime_settings()


def _fake_orchestrator():
    from types import SimpleNamespace

    risk = SimpleNamespace(
        max_risk_pct=0.5, max_daily_loss_pct=2.0, max_open_risk_pct=3.0,
        max_leverage=3.0, max_spot_positions=5, max_futures_positions=5,
    )
    simulator = SimpleNamespace(
        risk_manager=risk, initial_spot_balance=500.0, initial_futures_balance=500.0,
        spot_balance=500.0, futures_balance=500.0, spot_positions={},
        futures_positions={}, open_orders={}, closed_trades=[],
    )
    scanner = SimpleNamespace(
        enabled_markets={"SPOT", "FUTURES"}, analysis_timeframes=("15m", "1h"),
        analysis_symbol_limit=10,
    )
    return SimpleNamespace(
        simulator=simulator, scanner=scanner,
        _discovery=SimpleNamespace(spot_enabled=True, futures_enabled=True),
        telegram=None, _runtime_settings={},
    )


def test_apply_runtime_settings_updates_live_components(monkeypatch):
    from core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()
    saved = {}
    monkeypatch.setattr(runtime_settings_store, "save_runtime_settings", lambda value: saved.update(value))
    Orchestrator.apply_runtime_settings(orchestrator, {
        "risk_per_trade_pct": 0.75,
        "risk_max_total_open_pct": 4.0,
        "timeframes": ["5m", "15m", "1h"],
        "spot_enabled": True,
        "futures_enabled": False,
        "scan_all_eligible_symbols": True,
    })
    assert orchestrator.simulator.risk_manager.max_risk_pct == 0.75
    assert orchestrator.scanner.analysis_timeframes == ("5m", "15m", "1h")
    assert orchestrator.scanner.analysis_symbol_limit == 50
    assert orchestrator.scanner.enabled_markets == {"SPOT"}
    assert saved["risk_per_trade_pct"] == 0.75


def test_settings_persistence_failure_does_not_mutate_live_engine(monkeypatch):
    from core.orchestrator import Orchestrator

    orchestrator = _fake_orchestrator()

    def fail_save(_value):
        raise OSError("disk full")

    monkeypatch.setattr(runtime_settings_store, "save_runtime_settings", fail_save)
    with pytest.raises(OSError):
        Orchestrator.apply_runtime_settings(orchestrator, {"risk_per_trade_pct": 0.75})
    assert orchestrator.simulator.risk_manager.max_risk_pct == 0.5
    assert orchestrator.scanner.analysis_timeframes == ("15m", "1h")


def test_settings_reject_non_finite_values():
    with pytest.raises(ValidationError):
        SettingsRequest(risk_per_trade_pct=float("nan"))
    with pytest.raises(ValidationError):
        SettingsRequest(spot_initial_balance=float("inf"))
