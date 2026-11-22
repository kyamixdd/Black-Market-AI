"""Central configuration for BlackMarket AI.

All settings are loaded from environment variables with sensible defaults.
No secrets live in this file - use the private .env file.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR_OVERRIDE = os.environ.get("BLACKMARKET_DATA_DIR")
DATA_DIR = Path(_DATA_DIR_OVERRIDE).expanduser() if _DATA_DIR_OVERRIDE else BASE_DIR / "data"


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


APP_NAME = _env_str("APP_NAME", "BLACKMARKET_AI")
APP_ENV = _env_str("APP_ENV", "development")
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")

# --- Exchange ---
BINANCE_MARKET_DATA_ONLY = _env_bool("BINANCE_MARKET_DATA_ONLY", True)
BINANCE_API_KEY = _env_str("BINANCE_API_KEY", "")
BINANCE_API_SECRET = _env_str("BINANCE_API_SECRET", "")

# --- Market scanning ---
SCAN_ALL_ELIGIBLE_SYMBOLS = _env_bool("SCAN_ALL_ELIGIBLE_SYMBOLS", True)
SPOT_ENABLED = _env_bool("SPOT_ENABLED", True)
USDM_FUTURES_ENABLED = _env_bool("USDM_FUTURES_ENABLED", True)

TIMEFRAMES = _env_str("TIMEFRAMES", "1m,3m,5m,15m,30m,1h,4h,1d,1w").split(",")

# --- Paper capital ---
SPOT_INITIAL_BALANCE = _env_float("SPOT_INITIAL_BALANCE", 500.0)
FUTURES_INITIAL_BALANCE = _env_float("FUTURES_INITIAL_BALANCE", 500.0)
PAPER_TRADING_ENABLED = _env_bool("PAPER_TRADING_ENABLED", True)
REAL_TRADING_ENABLED = _env_bool("REAL_TRADING_ENABLED", False)

# --- Risk management ---
RISK_PER_TRADE_PCT = _env_float("RISK_PER_TRADE_PCT", 0.5)
RISK_MAX_DAILY_LOSS_PCT = _env_float("RISK_MAX_DAILY_LOSS_PCT", 2.0)
RISK_MAX_TOTAL_OPEN_PCT = _env_float("RISK_MAX_TOTAL_OPEN_PCT", 3.0)
RISK_MAX_LEVERAGE = _env_float("RISK_MAX_LEVERAGE", 3.0)
RISK_MAX_POSITION_SIZE_PCT = _env_float("RISK_MAX_POSITION_SIZE_PCT", 20.0)
RISK_MAX_ASSET_EXPOSURE_PCT = _env_float("RISK_MAX_ASSET_EXPOSURE_PCT", 30.0)
MAX_SPOT_POSITIONS = _env_int("MAX_SPOT_POSITIONS", 5)
MAX_FUTURES_POSITIONS = _env_int("MAX_FUTURES_POSITIONS", 5)

# --- Learning ---
LEARNING_MODE = _env_str("LEARNING_MODE", "hybrid")
ML_ENABLED = _env_bool("ML_ENABLED", True)
ADAPTIVE_LEARNING_ENABLED = _env_bool("ADAPTIVE_LEARNING_ENABLED", True)
AUTO_MODEL_TRAINING = _env_bool("AUTO_MODEL_TRAINING", True)
MODEL_VALIDATION_REQUIRED = _env_bool("MODEL_VALIDATION_REQUIRED", True)

# --- Telegram ---
TELEGRAM_ENABLED = _env_bool("TELEGRAM_ENABLED", False)
TELEGRAM_BOT_TOKEN = _env_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _env_str("TELEGRAM_CHAT_ID", "")

# --- Database ---
DATABASE_URL = _env_str("DATABASE_URL", f"sqlite:///{DATA_DIR / 'blackmarket.db'}")

# --- System safety ---
SIGNAL_STALE_SECONDS = _env_int("SIGNAL_STALE_SECONDS", 30)
AUTO_RECOVERY_ENABLED = _env_bool("AUTO_RECOVERY_ENABLED", True)
MODEL_ROLLBACK_ENABLED = _env_bool("MODEL_ROLLBACK_ENABLED", True)

# --- Scanner / websocket limits ---
MAX_WEBSOCKET_CONNECTIONS = _env_int("MAX_WEBSOCKET_CONNECTIONS", 12)
MAX_STREAMS_PER_CONNECTION = _env_int("MAX_STREAMS_PER_CONNECTION", 100)
MAX_CONCURRENT_SCANS = _env_int("MAX_CONCURRENT_SCANS", 8)
SCANNER_ANALYSIS_BATCH_SIZE = _env_int("SCANNER_ANALYSIS_BATCH_SIZE", 50)
SCANNER_STREAM_SYMBOL_LIMIT = _env_int("SCANNER_STREAM_SYMBOL_LIMIT", 100)
MIN_NOTIONAL = _env_float("MIN_NOTIONAL", 10.0)
SIGNAL_DEDUP_WINDOW_SECONDS = _env_int("SIGNAL_DEDUP_WINDOW_SECONDS", 300)

# --- Learning horizons ---
PREDICTION_HORIZON_MINUTES = _env_int("PREDICTION_HORIZON_MINUTES", 60)
WALK_FORWARD_MIN_SAMPLES = _env_int("WALK_FORWARD_MIN_SAMPLES", 500)
MODEL_RETRAIN_MIN_DAYS = _env_int("MODEL_RETRAIN_MIN_DAYS", 7)

# --- Model validation thresholds ---
MIN_VALIDATION_ACCURACY = _env_float("MIN_VALIDATION_ACCURACY", 0.52)
MIN_VALIDATION_F1 = _env_float("MIN_VALIDATION_F1", 0.50)
VALIDATION_METRIC = _env_str("VALIDATION_METRIC", "f1")

# --- River online learning ---
RIVER_LEARNING_RATE = _env_float("RIVER_LEARNING_RATE", 0.01)
RIVER_GRACE_PERIOD = _env_int("RIVER_GRACE_PERIOD", 100)

# --- Dataset ---
DATASET_VERSION_PREFIX = _env_str("DATASET_VERSION_PREFIX", "v")

# --- Paths ---
HISTORICAL_DIR = DATA_DIR / "historical"
CACHE_DIR = DATA_DIR / "cache"
BACKUP_DIR = DATA_DIR / "backups"
MODELS_DIR = Path(
    os.environ.get(
        "BLACKMARKET_MODELS_DIR",
        str(DATA_DIR / "models" if _DATA_DIR_OVERRIDE else BASE_DIR / "models"),
    )
)
LOG_DIR = Path(
    os.environ.get(
        "BLACKMARKET_LOG_DIR",
        str(DATA_DIR / "logs" if _DATA_DIR_OVERRIDE else BASE_DIR / "logs"),
    )
)

for _d in (DATA_DIR, HISTORICAL_DIR, CACHE_DIR, BACKUP_DIR, MODELS_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)