"""Stage 9 intelligence configuration validation and loading tests."""
import json

import pytest
from pydantic import ValidationError

from core import intelligence_config as config
from core import runtime_settings_store


@pytest.mark.parametrize("mode", ["balanced", "fast", "research", "conservative"])
def test_supported_modes_return_validated_presets(mode):
    settings = config.config_for_mode(mode)
    assert settings.mode.value == mode
    assert 1 <= settings.max_tool_calls <= 3


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        config.config_for_mode("unbounded")


@pytest.mark.parametrize("field,value", [
    ("max_tool_calls", 0), ("max_tool_calls", 4),
    ("response_detail", "verbose-ish"),
])
def test_invalid_configuration_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        config.IntelligenceConfig(**{field: value})


def test_extra_configuration_fields_are_rejected():
    with pytest.raises(ValidationError):
        config.IntelligenceConfig(unrestricted_execution=True)


def test_runtime_loader_reads_persisted_mode_and_profile(tmp_path, monkeypatch):
    target = tmp_path / "runtime_settings.json"
    target.write_text(json.dumps({
        "intelligence_mode": "research",
        "intelligence_config": {"max_tool_calls": 2, "response_detail": "detailed"},
    }), encoding="utf-8")
    monkeypatch.setattr(runtime_settings_store, "SETTINGS_PATH", target)
    monkeypatch.delenv("BLACKMARKET_INTELLIGENCE_MODE", raising=False)
    loaded = config.load_intelligence_config()
    assert loaded.mode is config.IntelligenceMode.RESEARCH
    assert loaded.max_tool_calls == 2
    assert loaded.response_detail == "detailed"


def test_environment_mode_overrides_persisted_mode(tmp_path, monkeypatch):
    target = tmp_path / "runtime_settings.json"
    target.write_text(json.dumps({"intelligence_mode": "research"}), encoding="utf-8")
    monkeypatch.setattr(runtime_settings_store, "SETTINGS_PATH", target)
    monkeypatch.setenv("BLACKMARKET_INTELLIGENCE_MODE", "fast")
    loaded = config.load_intelligence_config()
    assert loaded.mode is config.IntelligenceMode.FAST
    assert loaded.provider_enabled is False


def test_explicit_mode_override_has_highest_precedence(tmp_path, monkeypatch):
    target = tmp_path / "runtime_settings.json"
    target.write_text(json.dumps({"intelligence_mode": "research"}), encoding="utf-8")
    monkeypatch.setattr(runtime_settings_store, "SETTINGS_PATH", target)
    monkeypatch.setenv("BLACKMARKET_INTELLIGENCE_MODE", "fast")
    assert config.load_intelligence_config({"mode": "balanced"}).mode is config.IntelligenceMode.BALANCED


def test_invalid_persisted_config_fails_closed(tmp_path, monkeypatch):
    target = tmp_path / "runtime_settings.json"
    target.write_text(json.dumps({"intelligence_mode": "fast",
                                 "intelligence_config": {"max_tool_calls": 99}}),
                      encoding="utf-8")
    monkeypatch.setattr(runtime_settings_store, "SETTINGS_PATH", target)
    monkeypatch.delenv("BLACKMARKET_INTELLIGENCE_MODE", raising=False)
    with pytest.raises(RuntimeError, match="Invalid intelligence configuration"):
        config.load_intelligence_config()


def test_save_config_persists_and_refreshes_cache(tmp_path, monkeypatch):
    target = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(runtime_settings_store, "SETTINGS_PATH", target)
    config.get_runtime_intelligence_config.cache_clear()
    saved = config.save_intelligence_config(config.config_for_mode("fast"))
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored["intelligence_mode"] == "fast"
    assert stored["intelligence_config"]["max_tool_calls"] == 1
    assert saved.mode is config.IntelligenceMode.FAST
    config.get_runtime_intelligence_config.cache_clear()


def test_runtime_config_cache_can_be_reloaded(monkeypatch):
    monkeypatch.setattr(config, "load_intelligence_config",
                        lambda: config.config_for_mode("fast"))
    config.get_runtime_intelligence_config.cache_clear()
    assert config.get_runtime_intelligence_config().mode is config.IntelligenceMode.FAST
    assert config.reload_runtime_intelligence_config().mode is config.IntelligenceMode.FAST
    config.get_runtime_intelligence_config.cache_clear()
