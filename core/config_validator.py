"""Configuration validation at startup."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""


def validate_config() -> dict[str, Any]:
    """Validate all configuration values at startup.

    Returns:
        Dict of validated configuration values.

    Raises:
        ConfigValidationError: If any configuration value is invalid.
    """
    from config import (
        ADAPTIVE_LEARNING_ENABLED,
        APP_ENV,
        AUTO_MODEL_TRAINING,
        AUTO_RECOVERY_ENABLED,
        DATABASE_URL,
        DATASET_VERSION_PREFIX,
        FUTURES_INITIAL_BALANCE,
        LEARNING_MODE,
        LOG_LEVEL,
        MAX_CONCURRENT_SCANS,
        MAX_FUTURES_POSITIONS,
        MAX_SPOT_POSITIONS,
        MAX_STREAMS_PER_CONNECTION,
        MAX_WEBSOCKET_CONNECTIONS,
        MIN_VALIDATION_ACCURACY,
        MIN_VALIDATION_F1,
        ML_ENABLED,
        MODEL_RETRAIN_MIN_DAYS,
        MODEL_ROLLBACK_ENABLED,
        MODEL_VALIDATION_REQUIRED,
        PAPER_TRADING_ENABLED,
        PREDICTION_HORIZON_MINUTES,
        REAL_TRADING_ENABLED,
        RISK_MAX_DAILY_LOSS_PCT,
        RISK_MAX_LEVERAGE,
        RISK_MAX_TOTAL_OPEN_PCT,
        RISK_PER_TRADE_PCT,
        RIVER_GRACE_PERIOD,
        RIVER_LEARNING_RATE,
        SCAN_ALL_ELIGIBLE_SYMBOLS,
        SIGNAL_DEDUP_WINDOW_SECONDS,
        SIGNAL_STALE_SECONDS,
        SUPPORTED_TIMEFRAMES,
        SPOT_ENABLED,
        SPOT_INITIAL_BALANCE,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID,
        TELEGRAM_ENABLED,
        TIMEFRAMES,
        USDM_FUTURES_ENABLED,
        VALIDATION_METRIC,
        WALK_FORWARD_MIN_SAMPLES,
    )

    errors = []
    warnings = []

    # Validate APP_ENV
    valid_envs = {"development", "staging", "production", "test"}
    if APP_ENV not in valid_envs:
        errors.append(f"APP_ENV must be one of {valid_envs}, got: {APP_ENV}")

    # Validate LOG_LEVEL
    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if LOG_LEVEL not in valid_log_levels:
        errors.append(f"LOG_LEVEL must be one of {valid_log_levels}, got: {LOG_LEVEL}")

    # Validate market scanning
    if not SPOT_ENABLED and not USDM_FUTURES_ENABLED:
        errors.append("At least one of SPOT_ENABLED or USDM_FUTURES_ENABLED must be true")

    # Validate TIMEFRAMES
    valid_timeframes = set(SUPPORTED_TIMEFRAMES)
    for tf in TIMEFRAMES:
        if tf not in valid_timeframes:
            errors.append(f"Invalid timeframe: {tf}. Must be one of {valid_timeframes}")

    # Validate paper capital
    if SPOT_INITIAL_BALANCE <= 0:
        errors.append(f"SPOT_INITIAL_BALANCE must be positive, got: {SPOT_INITIAL_BALANCE}")
    if FUTURES_INITIAL_BALANCE <= 0:
        errors.append(f"FUTURES_INITIAL_BALANCE must be positive, got: {FUTURES_INITIAL_BALANCE}")

    # Validate trading mode
    if REAL_TRADING_ENABLED:
        errors.append("REAL_TRADING_ENABLED is unsupported; BlackMarket AI only supports paper trading")
    elif not PAPER_TRADING_ENABLED:
        warnings.append("PAPER_TRADING_ENABLED is false - no trading will occur")

    # Validate risk management
    if not (0 < RISK_PER_TRADE_PCT <= 10):
        errors.append(f"RISK_PER_TRADE_PCT must be between 0 and 10, got: {RISK_PER_TRADE_PCT}")
    if not (0 < RISK_MAX_DAILY_LOSS_PCT <= 20):
        errors.append(f"RISK_MAX_DAILY_LOSS_PCT must be between 0 and 20, got: {RISK_MAX_DAILY_LOSS_PCT}")
    if not (0 < RISK_MAX_TOTAL_OPEN_PCT <= 50):
        errors.append(f"RISK_MAX_TOTAL_OPEN_PCT must be between 0 and 50, got: {RISK_MAX_TOTAL_OPEN_PCT}")
    if not (1 <= RISK_MAX_LEVERAGE <= 20):
        errors.append(f"RISK_MAX_LEVERAGE must be between 1 and 20, got: {RISK_MAX_LEVERAGE}")
    if MAX_SPOT_POSITIONS <= 0:
        errors.append(f"MAX_SPOT_POSITIONS must be positive, got: {MAX_SPOT_POSITIONS}")
    if MAX_FUTURES_POSITIONS <= 0:
        errors.append(f"MAX_FUTURES_POSITIONS must be positive, got: {MAX_FUTURES_POSITIONS}")

    # Validate learning
    valid_learning_modes = {"hybrid", "ml_only", "rule_only"}
    if LEARNING_MODE not in valid_learning_modes:
        errors.append(f"LEARNING_MODE must be one of {valid_learning_modes}, got: {LEARNING_MODE}")

    if ML_ENABLED:
        if WALK_FORWARD_MIN_SAMPLES < 100:
            warnings.append(f"WALK_FORWARD_MIN_SAMPLES ({WALK_FORWARD_MIN_SAMPLES}) is low, may cause overfitting")
        if MODEL_RETRAIN_MIN_DAYS < 1:
            warnings.append(f"MODEL_RETRAIN_MIN_DAYS ({MODEL_RETRAIN_MIN_DAYS}) is very low")

    if MODEL_VALIDATION_REQUIRED:
        if not (0.5 <= MIN_VALIDATION_ACCURACY <= 1.0):
            errors.append(f"MIN_VALIDATION_ACCURACY must be between 0.5 and 1.0, got: {MIN_VALIDATION_ACCURACY}")
        if not (0.0 <= MIN_VALIDATION_F1 <= 1.0):
            errors.append(f"MIN_VALIDATION_F1 must be between 0.0 and 1.0, got: {MIN_VALIDATION_F1}")
        if VALIDATION_METRIC not in {"f1", "accuracy", "precision", "recall"}:
            errors.append(f"VALIDATION_METRIC must be one of f1, accuracy, precision, recall, got: {VALIDATION_METRIC}")

    # Validate River online learning
    if not (0.001 <= RIVER_LEARNING_RATE <= 1.0):
        errors.append(f"RIVER_LEARNING_RATE must be between 0.001 and 1.0, got: {RIVER_LEARNING_RATE}")
    if RIVER_GRACE_PERIOD < 1:
        errors.append(f"RIVER_GRACE_PERIOD must be >= 1, got: {RIVER_GRACE_PERIOD}")

    # Validate Telegram
    if TELEGRAM_ENABLED:
        if not TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required when TELEGRAM_ENABLED=true")
        if not TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID is required when TELEGRAM_ENABLED=true")

    # Validate DATABASE_URL
    if not DATABASE_URL.startswith("sqlite:///"):
        errors.append("DATABASE_URL must use SQLite; other database dialects are not supported")

    # Validate scanner/websocket limits
    if MAX_WEBSOCKET_CONNECTIONS < 1:
        errors.append(f"MAX_WEBSOCKET_CONNECTIONS must be >= 1, got: {MAX_WEBSOCKET_CONNECTIONS}")
    if MAX_STREAMS_PER_CONNECTION < 1:
        errors.append(f"MAX_STREAMS_PER_CONNECTION must be >= 1, got: {MAX_STREAMS_PER_CONNECTION}")
    if MAX_CONCURRENT_SCANS < 1:
        errors.append(f"MAX_CONCURRENT_SCANS must be >= 1, got: {MAX_CONCURRENT_SCANS}")

    # Validate signal settings
    if SIGNAL_STALE_SECONDS < 5:
        warnings.append(f"SIGNAL_STALE_SECONDS ({SIGNAL_STALE_SECONDS}) is very low")
    if SIGNAL_DEDUP_WINDOW_SECONDS < 60:
        warnings.append(f"SIGNAL_DEDUP_WINDOW_SECONDS ({SIGNAL_DEDUP_WINDOW_SECONDS}) is low")

    # Validate learning horizons
    if PREDICTION_HORIZON_MINUTES < 1:
        errors.append(f"PREDICTION_HORIZON_MINUTES must be >= 1, got: {PREDICTION_HORIZON_MINUTES}")
    if WALK_FORWARD_MIN_SAMPLES < 50:
        errors.append(f"WALK_FORWARD_MIN_SAMPLES must be >= 50, got: {WALK_FORWARD_MIN_SAMPLES}")

    # Validate dataset
    if not DATASET_VERSION_PREFIX:
        errors.append("DATASET_VERSION_PREFIX cannot be empty")

    # Report errors and warnings
    for warning in warnings:
        logger.warning("Config validation warning: %s", warning)

    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(error_msg)
        raise ConfigValidationError(error_msg)

    logger.info("Configuration validation passed")
    if warnings:
        logger.warning("Configuration has %d warnings", len(warnings))

    return {
        "APP_ENV": APP_ENV,
        "LOG_LEVEL": LOG_LEVEL,
        "SPOT_ENABLED": SPOT_ENABLED,
        "USDM_FUTURES_ENABLED": USDM_FUTURES_ENABLED,
        "SCAN_ALL_ELIGIBLE_SYMBOLS": SCAN_ALL_ELIGIBLE_SYMBOLS,
        "TIMEFRAMES": TIMEFRAMES,
        "SPOT_INITIAL_BALANCE": SPOT_INITIAL_BALANCE,
        "FUTURES_INITIAL_BALANCE": FUTURES_INITIAL_BALANCE,
        "PAPER_TRADING_ENABLED": PAPER_TRADING_ENABLED,
        "REAL_TRADING_ENABLED": REAL_TRADING_ENABLED,
        "RISK_PER_TRADE_PCT": RISK_PER_TRADE_PCT,
        "RISK_MAX_DAILY_LOSS_PCT": RISK_MAX_DAILY_LOSS_PCT,
        "RISK_MAX_TOTAL_OPEN_PCT": RISK_MAX_TOTAL_OPEN_PCT,
        "RISK_MAX_LEVERAGE": RISK_MAX_LEVERAGE,
        "MAX_SPOT_POSITIONS": MAX_SPOT_POSITIONS,
        "MAX_FUTURES_POSITIONS": MAX_FUTURES_POSITIONS,
        "LEARNING_MODE": LEARNING_MODE,
        "ML_ENABLED": ML_ENABLED,
        "ADAPTIVE_LEARNING_ENABLED": ADAPTIVE_LEARNING_ENABLED,
        "AUTO_MODEL_TRAINING": AUTO_MODEL_TRAINING,
        "MODEL_VALIDATION_REQUIRED": MODEL_VALIDATION_REQUIRED,
        "TELEGRAM_ENABLED": TELEGRAM_ENABLED,
        "TELEGRAM_BOT_TOKEN": "***" if TELEGRAM_BOT_TOKEN else "",
        "TELEGRAM_CHAT_ID": "***" if TELEGRAM_CHAT_ID else "",
        "DATABASE_URL": DATABASE_URL,
        "SIGNAL_STALE_SECONDS": SIGNAL_STALE_SECONDS,
        "AUTO_RECOVERY_ENABLED": AUTO_RECOVERY_ENABLED,
        "MODEL_ROLLBACK_ENABLED": MODEL_ROLLBACK_ENABLED,
    }


def validate_config_or_exit() -> dict[str, Any]:
    """Validate configuration and exit on failure.

    Returns:
        Dict of validated configuration values.
    """
    import sys
    try:
        return validate_config()
    except ConfigValidationError:
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = validate_config_or_exit()
    print("Validated configuration:")
    for k, v in result.items():
        print(f"  {k} = {v}")