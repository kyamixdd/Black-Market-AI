"""Database models for SQLite permanent memory."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def now_utc():
    return datetime.now(timezone.utc)


class SymbolModel(Base):
    __tablename__ = "symbols"

    symbol = Column(String(32), primary_key=True)
    market = Column(String(16), primary_key=True)  # SPOT or FUTURES
    base_asset = Column(String(16), nullable=False)
    quote_asset = Column(String(16), nullable=False)
    price_precision = Column(Integer, default=4)
    quantity_precision = Column(Integer, default=4)
    tick_size = Column(Float, default=0.0001)
    step_size = Column(Float, default=0.0001)
    min_notional = Column(Float, default=10.0)
    status = Column(String(16), default="TRADING")
    is_eligible = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=now_utc, onupdate=now_utc)


class CandleModel(Base):
    __tablename__ = "candles"

    symbol = Column(String(32), primary_key=True)
    market = Column(String(16), primary_key=True)
    timeframe = Column(String(8), primary_key=True)
    open_time = Column(Integer, primary_key=True)  # epoch ms
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    close_time = Column(Integer, nullable=False)
    quote_volume = Column(Float, default=0.0)
    trades_count = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_candle_sym_tf_time", "symbol", "market", "timeframe", "open_time"),
    )


class MarketSnapshotModel(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    market = Column(String(16), nullable=False)
    timestamp = Column(DateTime, default=now_utc)
    price = Column(Float, nullable=False)
    volume_24h = Column(Float, default=0.0)
    price_change_24h = Column(Float, default=0.0)
    mark_price = Column(Float, nullable=True)
    funding_rate = Column(Float, nullable=True)
    open_interest = Column(Float, nullable=True)
    bid_ask_spread = Column(Float, nullable=True)
    orderbook_imbalance = Column(Float, nullable=True)
    regime = Column(String(32), default="UNKNOWN")


class SignalModel(Base):
    __tablename__ = "signals"

    signal_id = Column(String(64), primary_key=True)
    symbol = Column(String(32), nullable=False)
    market = Column(String(16), nullable=False)
    strategy = Column(String(32), nullable=False)
    direction = Column(String(16), nullable=False)  # BUY, SELL, LONG, SHORT
    timeframe = Column(String(8), nullable=False)
    entry = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Text, nullable=False)  # JSON list
    raw_score = Column(Float, nullable=False)
    reasons = Column(Text, nullable=False)  # JSON list
    status = Column(String(32), default="PROPOSED")  # PROPOSED, VALIDATED, REJECTED, EXPIRED, EXECUTED
    created_at = Column(DateTime, default=now_utc)
    confidence = Column(Float, default=0.0)


class PredictionModel(Base):
    __tablename__ = "predictions"

    prediction_id = Column(String(64), primary_key=True)
    signal_id = Column(String(64), nullable=True)
    symbol = Column(String(32), nullable=False)
    market = Column(String(16), nullable=False)
    timeframe = Column(String(8), nullable=True)
    model_version = Column(String(32), nullable=False)
    strategy_version = Column(String(32), nullable=True)
    regime = Column(String(32), nullable=True)
    horizon_minutes = Column(Integer, default=60)
    prob_up = Column(Float, nullable=False)
    prob_down = Column(Float, nullable=False)
    prob_flat = Column(Float, nullable=False)
    predicted_class = Column(String(16), nullable=False)  # UP, DOWN, FLAT
    confidence = Column(Float, nullable=False)
    feature_values = Column(Text, nullable=True)  # JSON blob of features used
    created_at = Column(DateTime, default=now_utc)
    eval_time = Column(DateTime, nullable=True)
    actual_outcome = Column(String(16), nullable=True)  # UP, DOWN, FLAT
    actual_return_pct = Column(Float, nullable=True)
    simulated_pnl = Column(Float, nullable=True)
    transaction_costs = Column(Float, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    evaluation_notes = Column(Text, nullable=True)


class PaperOrderModel(Base):
    __tablename__ = "paper_orders"

    order_id = Column(String(64), primary_key=True)
    signal_id = Column(String(64), nullable=True)
    symbol = Column(String(32), nullable=False)
    market = Column(String(16), nullable=False)
    order_type = Column(String(16), nullable=False)  # MARKET, LIMIT
    side = Column(String(16), nullable=False)  # BUY, SELL, LONG, SHORT
    amount = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    status = Column(String(32), default="OPEN")
    filled_amount = Column(Float, default=0.0)
    avg_fill_price = Column(Float, default=0.0)
    fee = Column(Float, default=0.0)
    leverage = Column(Float, default=1.0)
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc)


class PaperPositionModel(Base):
    __tablename__ = "paper_positions"

    position_id = Column(String(64), primary_key=True)
    symbol = Column(String(32), nullable=False)
    market = Column(String(16), nullable=False)
    side = Column(String(16), nullable=False)  # LONG, SHORT, SPOT
    entry_price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    leverage = Column(Float, default=1.0)
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    fees_paid = Column(Float, default=0.0)
    last_funding_time = Column(Integer, default=0)
    reserved_notional = Column(Float, default=0.0)
    reserved_margin = Column(Float, default=0.0)
    order_id = Column(String(64), nullable=True)
    signal_id = Column(String(64), nullable=True)
    strategy = Column(String(32), default="UNKNOWN")
    order_type = Column(String(16), default="MARKET")
    status = Column(String(16), default="OPEN")  # OPEN, CLOSED, LIQUIDATED
    opened_at = Column(DateTime, default=now_utc)
    closed_at = Column(DateTime, nullable=True)
    close_price = Column(Float, nullable=True)


class TradeHistoryModel(Base):
    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(String(64), nullable=False)
    symbol = Column(String(32), nullable=False)
    market = Column(String(16), nullable=False)
    side = Column(String(16), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    leverage = Column(Float, default=1.0)
    pnl = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)
    strategy = Column(String(32), default="UNKNOWN")
    signal_id = Column(String(64), nullable=True)
    order_id = Column(String(64), nullable=True)
    opened_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, default=now_utc)
    close_reason = Column(String(32), default="TAKE_PROFIT")


class StrategyMetricsModel(Base):
    __tablename__ = "strategy_metrics"

    strategy = Column(String(32), primary_key=True)
    market = Column(String(16), primary_key=True)
    total_signals = Column(Integer, default=0)
    validated_signals = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    weight = Column(Float, default=1.0)
    last_updated = Column(DateTime, default=now_utc)


class ModelRegistryModel(Base):
    __tablename__ = "model_registry"

    version = Column(String(32), primary_key=True)
    model_type = Column(String(32), nullable=False)  # random_forest, xgboost, river
    trained_at = Column(DateTime, default=now_utc)
    metrics = Column(Text, nullable=False)  # JSON
    file_path = Column(String(256), nullable=False)
    status = Column(String(32), default="VALIDATED")  # CANDIDATE, VALIDATED, CHALLENGER, CHAMPION, ROLLED_BACK
    is_active = Column(Boolean, default=False)
    is_champion = Column(Boolean, default=False)
    parent_version = Column(String(32), nullable=True)  # For lineage tracking
    evaluation_data = Column(Text, nullable=True)  # JSON: evaluation criteria results
    promotion_criteria = Column(Text, nullable=True)  # JSON: criteria that were met/failed
    rollback_checkpoint = Column(Boolean, default=False)  # Can rollback to this version


class LearningRunModel(Base):
    __tablename__ = "learning_runs"

    run_id = Column(String(64), primary_key=True)
    started_at = Column(DateTime, default=now_utc)
    finished_at = Column(DateTime, nullable=True)
    samples_count = Column(Integer, default=0)
    accuracy = Column(Float, nullable=True)
    loss = Column(Float, nullable=True)
    status = Column(String(32), default="IN_PROGRESS")
    summary = Column(Text, nullable=True)


class NotificationModel(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=now_utc)
    alert_type = Column(String(32), nullable=False)
    title = Column(String(128), nullable=False)
    message = Column(Text, nullable=False)
    delivered = Column(Boolean, default=False)
    error = Column(Text, nullable=True)


class SystemEventModel(Base):
    __tablename__ = "system_events"

    event_id = Column(String(64), primary_key=True)
    event_type = Column(String(64), nullable=False)
    timestamp = Column(DateTime, default=now_utc)
    source = Column(String(64), nullable=False)
    symbol = Column(String(32), nullable=True)
    market = Column(String(16), nullable=True)
    payload = Column(Text, nullable=False)



class SavedStrategyModel(Base):
    """Versioned user-authored strategy definitions."""
    __tablename__ = "saved_strategies"

    strategy_id = Column(String(64), primary_key=True)
    name = Column(String(120), nullable=False)
    strategy_key = Column(String(64), nullable=False)
    description = Column(Text, nullable=False, default="")
    definition_json = Column(Text, nullable=False)
    tags_json = Column(Text, nullable=False, default="[]")
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)


class BacktestReportModel(Base):
    """Immutable saved research report and its full configuration/results."""
    __tablename__ = "backtest_reports"

    report_id = Column(String(64), primary_key=True)
    strategy_id = Column(String(64), nullable=True, index=True)
    strategy_name = Column(String(120), nullable=False)
    symbol = Column(String(32), nullable=False, index=True)
    market = Column(String(16), nullable=False)
    timeframe = Column(String(8), nullable=False)
    status = Column(String(32), nullable=False)
    config_json = Column(Text, nullable=False)
    report_json = Column(Text, nullable=False)
    origin = Column(String(32), nullable=False, default="USER_SUBMITTED")
    created_at = Column(DateTime, default=now_utc, nullable=False, index=True)


class WorkspaceModel(Base):
    """User-saved dashboard/workspace state with schema versioning."""
    __tablename__ = "workspaces"

    workspace_id = Column(String(64), primary_key=True)
    name = Column(String(120), nullable=False)
    owner_key = Column(String(64), nullable=False, default="local", index=True)
    schema_version = Column(Integer, nullable=False, default=1)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)




class PublicStrategyModel(Base):
    """Public community entry; deliberately stores only publication-safe data."""
    __tablename__ = "public_strategies"

    public_id = Column(String(64), primary_key=True)
    owner_key = Column(String(64), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    strategy_key = Column(String(64), nullable=False, index=True)
    rules_json = Column(Text, nullable=False)
    assets_json = Column(Text, nullable=False, default="[]")
    timeframes_json = Column(Text, nullable=False, default="[]")
    risk_json = Column(Text, nullable=False, default="{}")
    limitations_json = Column(Text, nullable=False, default="[]")
    report_json = Column(Text, nullable=False, default="{}")
    report_sha256 = Column(String(64), nullable=False, default="")
    source_report_id = Column(String(64), nullable=True)
    report_provenance = Column(String(32), nullable=False, default="USER_SUBMITTED")
    version = Column(Integer, nullable=False, default=1)
    visibility = Column(String(16), nullable=False, default="PUBLIC")
    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)


class PublicStrategyVersionModel(Base):
    """Immutable publication snapshots for community version history."""
    __tablename__ = "public_strategy_versions"

    version_id = Column(String(64), primary_key=True)
    public_id = Column(String(64), nullable=False, index=True)
    owner_key = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    snapshot_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)


class StrategyFavoriteModel(Base):
    __tablename__ = "strategy_favorites"

    owner_key = Column(String(64), primary_key=True)
    public_id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)


class StrategyReportFlagModel(Base):
    __tablename__ = "strategy_report_flags"

    flag_id = Column(String(64), primary_key=True)
    public_id = Column(String(64), nullable=False, index=True)
    reporter_key = Column(String(64), nullable=False, index=True)
    reason = Column(String(32), nullable=False)
    details = Column(Text, nullable=False, default="")
    status = Column(String(16), nullable=False, default="OPEN")
    created_at = Column(DateTime, default=now_utc, nullable=False)


def create_all(db_path: str) -> None:
    engine = create_engine(db_path, future=True)
    Base.metadata.create_all(engine)