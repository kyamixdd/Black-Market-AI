"""Test configuration management."""
import os
import importlib

import pytest

from config import _env_bool, _env_float, _env_int, _env_str


def test_env_helpers(monkeypatch):
    # Test str
    os.environ["TEST_STR"] = "val"
    assert _env_str("TEST_STR", "default") == "val"
    assert _env_str("TEST_MISSING", "default") == "default"

    # Test bool
    monkeypatch.setenv("TEST_BOOL_T", "true")
    monkeypatch.setenv("TEST_BOOL_F", "false")
    assert _env_bool("TEST_BOOL_T", False) is True
    assert _env_bool("TEST_BOOL_F", True) is False
    assert _env_bool("TEST_MISSING", True) is True
    monkeypatch.setenv("TEST_INVALID_BOOL", "sometimes")
    with pytest.raises(ValueError, match="TEST_INVALID_BOOL must be a boolean value"):
        _env_bool("TEST_INVALID_BOOL", False)

    # Test float
    monkeypatch.setenv("TEST_FLOAT", "1.23")
    assert _env_float("TEST_FLOAT", 0.0) == 1.23
    monkeypatch.setenv("TEST_INVALID_FLOAT", "not-a-number")
    with pytest.raises(ValueError):
        _env_float("TEST_INVALID_FLOAT", 9.9)

    # Test int
    monkeypatch.setenv("TEST_INT", "42")
    assert _env_int("TEST_INT", 0) == 42
    monkeypatch.setenv("TEST_INVALID_INT", "not-an-int")
    with pytest.raises(ValueError):
        _env_int("TEST_INVALID_INT", 7)


def test_telegram_is_opt_in(monkeypatch):
    import config

    original_value = os.environ.get("TELEGRAM_ENABLED")
    try:
        monkeypatch.delenv("TELEGRAM_ENABLED", raising=False)
        importlib.reload(config)
        assert config.TELEGRAM_ENABLED is False
    finally:
        if original_value is None:
            monkeypatch.delenv("TELEGRAM_ENABLED", raising=False)
        else:
            monkeypatch.setenv("TELEGRAM_ENABLED", original_value)
        importlib.reload(config)


def test_real_trading_configuration_is_rejected(monkeypatch):
    import config
    from core.config_validator import ConfigValidationError, validate_config

    with monkeypatch.context() as patch:
        patch.setenv("PAPER_TRADING_ENABLED", "true")
        patch.setenv("REAL_TRADING_ENABLED", "true")
        patch.setenv("TELEGRAM_ENABLED", "false")
        importlib.reload(config)

        with pytest.raises(ConfigValidationError, match="REAL_TRADING_ENABLED is unsupported"):
            validate_config()

    importlib.reload(config)


def test_non_sqlite_database_configuration_is_rejected(monkeypatch):
    import config
    from core.config_validator import ConfigValidationError, validate_config

    with monkeypatch.context() as patch:
        patch.setenv("DATABASE_URL", "postgresql://localhost/blackmarket")
        patch.setenv("PAPER_TRADING_ENABLED", "true")
        patch.setenv("REAL_TRADING_ENABLED", "false")
        patch.setenv("TELEGRAM_ENABLED", "false")
        importlib.reload(config)

        with pytest.raises(ConfigValidationError, match="DATABASE_URL must use SQLite"):
            validate_config()

    importlib.reload(config)
