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
