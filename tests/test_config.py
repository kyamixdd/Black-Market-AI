"""Test configuration management."""
import os
import importlib

from config import _env_bool, _env_float, _env_int, _env_str


def test_env_helpers():
    # Test str
    os.environ["TEST_STR"] = "val"
    assert _env_str("TEST_STR", "default") == "val"
    assert _env_str("TEST_MISSING", "default") == "default"

    # Test bool
    os.environ["TEST_BOOL_T"] = "true"
    os.environ["TEST_BOOL_F"] = "false"
    assert _env_bool("TEST_BOOL_T", False) is True
    assert _env_bool("TEST_BOOL_F", True) is False
    assert _env_bool("TEST_MISSING", True) is True

    # Test float
    os.environ["TEST_FLOAT"] = "1.23"
    assert _env_float("TEST_FLOAT", 0.0) == 1.23
    assert _env_float("TEST_INVALID_FLOAT", 9.9) == 9.9

    # Test int
    os.environ["TEST_INT"] = "42"
    assert _env_int("TEST_INT", 0) == 42
    assert _env_int("TEST_INVALID_INT", 7) == 7


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

    monkeypatch.setattr(config, "PAPER_TRADING_ENABLED", False)
    monkeypatch.setattr(config, "REAL_TRADING_ENABLED", True)

    try:
        validate_config()
    except ConfigValidationError as exc:
        assert "REAL_TRADING_ENABLED is unsupported" in str(exc)
    else:
        raise AssertionError("Real trading configuration must never be accepted")


def test_database_url_credentials_are_redacted_from_validation_output(monkeypatch, caplog):
    import logging
    import config
    from core.config_validator import validate_config

    monkeypatch.setattr(
        config,
        "DATABASE_URL",
        "postgresql+psycopg://blackmarket:top-secret-password@db.example:5432/blackmarket",
    )
    with caplog.at_level(logging.WARNING):
        result = validate_config()

    assert result["DATABASE_URL"] == "postgresql+psycopg://blackmarket:***@db.example:5432/blackmarket"
    assert "top-secret-password" not in caplog.text
