"""Pydantic schemas for API requests and responses."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class MarketType(str, Enum):
    SPOT = "SPOT"
    FUTURES = "FUTURES"


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"
    WAIT = "WAIT"


class SignalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"


class EventType(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    SIGNAL_PROPOSED = "SIGNAL_PROPOSED"
    SIGNAL_VALIDATED = "SIGNAL_VALIDATED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    PREDICTION = "PREDICTION"
    TRADE_PROPOSED = "TRADE_PROPOSED"
    TRADE_EXECUTED = "TRADE_EXECUTED"
    TRADE_PARTIALLY_FILLED = "TRADE_PARTIALLY_FILLED"
    TRADE_CLOSED = "TRADE_CLOSED"
    TRADE_CANCELLED = "TRADE_CANCELLED"
    TRADE_REJECTED = "TRADE_REJECTED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_FILLED = "ORDER_FILLED"
    LEARNING_UPDATE = "LEARNING_UPDATE"
    MODEL_TRAINED = "MODEL_TRAINED"
    MODEL_PROMOTED = "MODEL_PROMOTED"
    MODEL_ROLLED_BACK = "MODEL_ROLLED_BACK"
    RISK_ALERT = "RISK_ALERT"
    SYSTEM_HEALTH = "SYSTEM_HEALTH"
    NOTIFICATION = "NOTIFICATION"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class MarketSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    market: MarketType
    timestamp: datetime
    price: float
    volume_24h: float
    price_change_24h: float
    mark_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    bid_ask_spread: float | None = None
    orderbook_imbalance: float | None = None
    regime: str


class MarketListResponse(BaseModel):
    markets: list[MarketSnapshotResponse]
    total: int
    spot_count: int
    futures_count: int


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_id: str
    symbol: str
    market: MarketType
    strategy: str
    direction: SignalDirection
    timeframe: str
    entry: float
    stop_loss: float
    take_profit: list[float]
    raw_score: float
    confidence: float
    regime: str
    timeframe: str
    reasons: list[str]
    status: SignalStatus
    created_at: datetime
    data_freshness: str = "LIVE"
    weight: float | None = None


class SignalListResponse(BaseModel):
    signals: list[SignalResponse]
    total: int


class PortfolioBalanceResponse(BaseModel):
    spot_balance: float
    futures_balance: float
    total_balance: float
    spot_pnl: float
    futures_pnl: float
    total_pnl: float
    spot_return_pct: float
    futures_return_pct: float
    total_return_pct: float


class PositionResponse(BaseModel):
    position_id: str
    symbol: str
    market: MarketType
    side: str
    entry_price: float
    current_price: float
    amount: float
    leverage: float
    unrealized_pnl: float
    realized_pnl: float
    fees_paid: float
    reserved_margin: float = 0.0
    reserved_notional: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    liquidation_price: float | None = None
    margin_ratio: float | None = None
    status: str
    opened_at: datetime
    strategy: str | None = None


class PositionListResponse(BaseModel):
    positions: list[PositionResponse]
    total: int
    spot_count: int
    futures_count: int
    total_unrealized_pnl: float
    total_fees_paid: float


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_id: str
    symbol: str
    market: MarketType
    side: str
    entry_price: float
    exit_price: float
    amount: float
    leverage: float
    pnl: float
    pnl_pct: float
    fee: float
    strategy: str
    opened_at: datetime
    closed_at: datetime
    close_reason: str


class TradeListResponse(BaseModel):
    trades: list[TradeResponse]
    total: int
    total_pnl: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float


class StrategyMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy: str
    market: MarketType
    total_signals: int
    validated_signals: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    profit_factor: float
    weight: float


class StrategyMetricsListResponse(BaseModel):
    metrics: list[StrategyMetricsResponse]


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prediction_id: str
    symbol: str
    market: MarketType
    timeframe: str | None = None
    model_version: str
    strategy_version: str | None = None
    regime: str | None = None
    horizon_minutes: int
    prob_up: float
    prob_down: float
    prob_flat: float
    predicted_class: str
    confidence: float
    created_at: datetime
    eval_time: datetime | None = None
    actual_outcome: str | None = None
    actual_return_pct: float | None = None
    simulated_pnl: float | None = None
    transaction_costs: float | None = None
    is_correct: bool | None = None
    evaluation_notes: str | None = None


class PredictionListResponse(BaseModel):
    predictions: list[PredictionResponse]
    total: int
    resolved_count: int
    accuracy: float


class LearningStatusResponse(BaseModel):
    model_status: str
    rf_loaded: bool
    xgb_loaded: bool
    river_available: bool
    version: str | None = None
    predictions_total: int
    predictions_resolved: int
    accuracy: float
    recent_predictions: list[PredictionResponse]


class ModelRegistryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: str
    model_type: str
    trained_at: datetime
    metrics: dict[str, Any]
    file_path: str
    status: str
    is_active: bool
    is_champion: bool
    parent_version: str | None = None
    evaluation_data: dict[str, Any] | None = None
    promotion_criteria: dict[str, Any] | None = None
    rollback_checkpoint: bool


class ModelRegistryListResponse(BaseModel):
    models: list[ModelRegistryResponse]


class RiskMetricsResponse(BaseModel):
    current_exposure_pct: float
    used_risk_capacity_pct: float
    available_risk_capacity_pct: float
    open_trade_risk_pct: float
    daily_loss_capacity_pct: float
    risk_manager_status: str
    max_spot_positions: int
    max_futures_positions: int
    max_leverage: float
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_total_open_pct: float


class SystemHealthResponse(BaseModel):
    status: HealthStatus
    components: dict[str, dict[str, Any]]
    metrics: dict[str, float]
    uptime_seconds: float


class SystemEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: str
    timestamp: datetime
    source: str
    symbol: str | None = None
    market: str | None = None
    payload: dict[str, Any]


class SystemEventListResponse(BaseModel):
    events: list[SystemEventResponse]
    total: int


class MarketHeatmapResponse(BaseModel):
    symbol: str
    market: MarketType
    price_change_24h: float
    volume_24h: float
    price: float
    regime: str


class MarketHeatmapResponse(BaseModel):
    heatmap: list[MarketHeatmapResponse]


class MarketBreadthResponse(BaseModel):
    advancing: int
    declining: int
    neutral: int
    total_volume: float
    avg_spread_bps: float
    avg_orderbook_imbalance: float


class VolumeResponse(BaseModel):
    buy_volume: float
    sell_volume: float
    total_volume: float
    volume_change_24h: float
    buy_volume_7d_avg: float | None = None
    sell_volume_7d_avg: float | None = None


class LongShortResponse(BaseModel):
    long_short_ratio: float
    open_interest: float
    funding_rate: float
    long_volume: float
    short_volume: float


class RiskAlertResponse(BaseModel):
    alert_type: str
    message: str
    symbol: str | None = None
    market: str | None = None
    margin_ratio: float | None = None
    mark_price: float | None = None
    liquidation_price: float | None = None
    timestamp: datetime


class SignalRequest(BaseModel):
    symbol: str
    market: MarketType
    strategy: str
    direction: SignalDirection
    timeframe: str
    entry: float
    stop_loss: float
    take_profit: list[float]
    confidence: float
    regime: str
    reasons: list[str]


class SettingsRequest(BaseModel):
    spot_enabled: bool | None = None
    futures_enabled: bool | None = None
    scan_all_eligible_symbols: bool | None = None
    timeframes: list[str] | None = None
    spot_initial_balance: float | None = None
    futures_initial_balance: float | None = None
    risk_per_trade_pct: float | None = None
    risk_max_daily_loss_pct: float | None = None
    risk_max_total_open_pct: float | None = None
    risk_max_leverage: float | None = None
    max_spot_positions: int | None = None
    max_futures_positions: int | None = None
    telegram_enabled: bool | None = None


class SettingsResponse(BaseModel):
    spot_enabled: bool
    futures_enabled: bool
    scan_all_eligible_symbols: bool
    timeframes: list[str]
    spot_initial_balance: float
    futures_initial_balance: float
    risk_per_trade_pct: float
    risk_max_daily_loss_pct: float
    risk_max_total_open_pct: float
    risk_max_leverage: float
    max_spot_positions: int
    max_futures_positions: int
    telegram_enabled: bool
    telegram_bot_token_configured: bool
    telegram_chat_id_configured: bool


class HealthResponse(BaseModel):
    status: str
    backend_ready: bool
    websocket_connected: bool
    database_connected: bool
    market_data_active: bool
    learning_active: bool
    paper_trading_active: bool
    uptime_seconds: float
    version: str


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: int = 500


class SuccessResponse(BaseModel):
    success: bool = True
    message: str | None = None