"""Pydantic schemas for API requests and responses."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


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


class WebSocketChannel(str, Enum):
    MARKET_UPDATES = "market_updates"
    PRICE_UPDATES = "price_updates"
    SIGNAL_UPDATES = "signal_updates"
    PORTFOLIO_UPDATES = "portfolio_updates"
    POSITION_UPDATES = "position_updates"
    RISK_UPDATES = "risk_updates"
    SYSTEM_EVENTS = "system_events"
    LEARNING_UPDATES = "learning_updates"


class WebSocketClientMessage(BaseModel):
    type: Literal["subscribe", "unsubscribe", "ping"]
    channels: list[WebSocketChannel] = Field(default_factory=list)


class WebSocketAcknowledgement(BaseModel):
    type: Literal["authenticated", "subscribed", "unsubscribed", "pong", "error"]
    channels: list[WebSocketChannel] = Field(default_factory=list)
    detail: str | None = None


class MarketSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    market: MarketType
    timestamp: datetime | None
    price: float
    volume_24h: float | None
    price_change_24h: float | None
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


class CandleResponse(BaseModel):
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int


class CandleListResponse(BaseModel):
    symbol: str
    market: MarketType
    timeframe: str
    candles: list[CandleResponse]


class MarketSymbolResponse(BaseModel):
    symbol: str
    market: MarketType
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    tick_size: float
    step_size: float
    min_notional: float
    status: str
    is_eligible: bool
    price: float
    price_change_24h: float | None
    volume_24h: float | None
    regime: str


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
    daily_pnl: float = Field(0.0, description="Realized P&L from trades closed during the current UTC day.")
    monthly_pnl: float = Field(0.0, description="Realized P&L from trades closed during the current UTC month.")
    realized_pnl: float = Field(0.0, description="Realized P&L across completed trades.")
    unrealized_pnl: float = Field(0.0, description="Current unrealized P&L across open positions.")
    drawdown_pct: float = 0.0


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
    stop_loss: float | None = None
    take_profit: float | None = None
    liquidation_price: float | None = None
    margin_ratio: float | None = None
    status: str
    opened_at: datetime | None
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
    opened_at: datetime | None
    closed_at: datetime | None
    close_reason: str


class TradeListResponse(BaseModel):
    trades: list[TradeResponse]
    total: int
    total_pnl: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float


class TradeStatisticsResponse(BaseModel):
    total: int
    total_pnl: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float


class SignalStatisticsResponse(BaseModel):
    total: int
    avg_confidence: float
    by_direction: dict[str, int]
    by_strategy: dict[str, int]


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


class StrategyWeightResponse(BaseModel):
    base_weight: float
    regime_adjusted: float


class LongShortHistoryResponse(BaseModel):
    timestamp: datetime
    ratio: float


class IntelligenceSummaryResponse(BaseModel):
    strategies: list[StrategyMetricsResponse]
    strategy_weights: dict[str, StrategyWeightResponse]


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
    trained_at: datetime | None
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
    unmeasured_positions: int = 0


class SystemHealthResponse(BaseModel):
    status: str
    components: dict[str, dict[str, Any]]
    metrics: dict[str, Any]
    uptime_seconds: float


class SystemEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: str
    timestamp: datetime | None
    source: str
    symbol: str | None = None
    market: str | None = None
    payload: dict[str, Any]


class RiskAlertListResponse(BaseModel):
    alerts: list[SystemEventResponse]
    total: int


class WebSocketEventMessage(BaseModel):
    type: Literal["event"] = "event"
    channel: WebSocketChannel
    event: SystemEventResponse


class SystemEventListResponse(BaseModel):
    events: list[SystemEventResponse]
    total: int


class MarketHeatmapItemResponse(BaseModel):
    symbol: str
    market: MarketType
    price_change_24h: float
    volume_24h: float
    price: float
    regime: str
    relative_strength_pct: float | None = None
    volume_rank_pct: float | None = None
    volatility_24h_pct: float | None = None


class MarketHeatmapResponse(BaseModel):
    heatmap: list[MarketHeatmapItemResponse]


class MarketBreadthResponse(BaseModel):
    advancing: int
    declining: int
    neutral: int
    total_volume: float
    avg_spread_bps: float | None = None
    avg_orderbook_imbalance: float | None = None


class VolumeResponse(BaseModel):
    symbol: str
    market: MarketType
    buy_volume: float | None = None
    sell_volume: float | None = None
    total_volume: float
    volume_change_24h: float | None = None
    buy_volume_7d_avg: float | None = None
    sell_volume_7d_avg: float | None = None
    flow_is_estimated: bool = False
    flow_sample_size: int = 0
    flow_sample_scope: str | None = None
    flow_last_trade_time: datetime | None = None


class LongShortResponse(BaseModel):
    symbol: str
    long_short_ratio: float | None = None
    open_interest: float | None = None
    funding_rate: float | None = None
    long_volume: float | None = None
    short_volume: float | None = None
    sample_period: str | None = None
    last_updated: datetime | None = None
    history: list[LongShortHistoryResponse] = Field(default_factory=list)


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
    model_config = ConfigDict(extra="forbid")

    spot_enabled: bool | None = None
    futures_enabled: bool | None = None
    scan_all_eligible_symbols: bool | None = None
    timeframes: list[str] | None = None
    spot_initial_balance: float | None = Field(default=None, gt=0, le=1_000_000_000)
    futures_initial_balance: float | None = Field(default=None, gt=0, le=1_000_000_000)
    risk_per_trade_pct: float | None = Field(default=None, gt=0, le=10)
    risk_max_daily_loss_pct: float | None = Field(default=None, gt=0, le=20)
    risk_max_total_open_pct: float | None = Field(default=None, gt=0, le=50)
    risk_max_leverage: float | None = Field(default=None, ge=1, le=20)
    max_spot_positions: int | None = Field(default=None, ge=1, le=100)
    max_futures_positions: int | None = Field(default=None, ge=1, le=100)
    telegram_enabled: bool | None = None

    @field_validator('timeframes')
    @classmethod
    def validate_timeframes(cls, value):
        allowed = {"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}
        if value is not None and (
            not value or len(value) != len(set(value)) or any(item not in allowed for item in value)
        ):
            raise ValueError("timeframes must be a non-empty unique list of supported intervals")
        return value


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
    restart_required: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    backend_ready: bool
    websocket_connected: bool
    exchange_websocket_connected: bool = False
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