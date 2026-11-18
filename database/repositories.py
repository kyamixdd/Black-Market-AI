"""Database repository classes for accessing and persisting intelligence data."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import (
    CandleModel,
    MarketSnapshotModel,
    ModelRegistryModel,
    NotificationModel,
    PaperOrderModel,
    PaperPositionModel,
    PredictionModel,
    SignalModel,
    StrategyMetricsModel,
    SymbolModel,
    SystemEventModel,
    SimulatorStateModel,
    TradeHistoryModel,
)

logger = logging.getLogger(__name__)


class Repository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    def _get_session(self) -> Session:
        return self._session_maker()

    # --- Symbol Repo ---
    def save_symbols(self, symbols: list[dict[str, Any]]) -> int:
        with self._get_session() as session:
            count = 0
            for item in symbols:
                existing = session.get(SymbolModel, (item["symbol"], item["market"]))
                if existing:
                    for k, v in item.items():
                        setattr(existing, k, v)
                    existing.last_updated = datetime.now(timezone.utc)
                else:
                    obj = SymbolModel(**item)
                    session.add(obj)
                count += 1
            session.commit()
            return count

    def get_eligible_symbols(self, market: str | None = None) -> list[SymbolModel]:
        with self._get_session() as session:
            stmt = select(SymbolModel).where(SymbolModel.is_eligible.is_(True))
            if market:
                stmt = stmt.where(SymbolModel.market == market)
            return list(session.scalars(stmt).all())

    # --- Candle Repo ---
    def save_candles(self, candles: list[dict[str, Any]]) -> int:
        if not candles:
            return 0
        with self._get_session() as session:
            saved = 0
            for c in candles:
                pk = (c["symbol"], c["market"], c["timeframe"], c["open_time"])
                existing = session.get(CandleModel, pk)
                if existing:
                    for k, v in c.items():
                        setattr(existing, k, v)
                else:
                    session.add(CandleModel(**c))
                saved += 1
            session.commit()
            return saved

    def get_candles(self, symbol: str, market: str, timeframe: str, limit: int = 200) -> list[CandleModel]:
        with self._get_session() as session:
            stmt = (
                select(CandleModel)
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.market == market,
                    CandleModel.timeframe == timeframe,
                )
                .order_by(CandleModel.open_time.desc())
                .limit(limit)
            )
            candles = list(session.scalars(stmt).all())
            candles.reverse()
            return candles

    # --- Market Snapshot ---
    def save_snapshot(self, snapshot: dict[str, Any]) -> int:
        with self._get_session() as session:
            obj = MarketSnapshotModel(**snapshot)
            session.add(obj)
            session.commit()
            return obj.id

    def get_latest_snapshot(self, symbol: str, market: str) -> MarketSnapshotModel | None:
        with self._get_session() as session:
            stmt = (
                select(MarketSnapshotModel)
                .where(MarketSnapshotModel.symbol == symbol, MarketSnapshotModel.market == market)
                .order_by(MarketSnapshotModel.timestamp.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()

    def get_recent_snapshots(self, limit: int = 1000) -> list[MarketSnapshotModel]:
        with self._get_session() as session:
            stmt = (
                select(MarketSnapshotModel)
                .order_by(MarketSnapshotModel.timestamp.desc(), MarketSnapshotModel.id.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    # --- Signal Repo ---
    def save_signal(self, signal: dict[str, Any]) -> str:
        with self._get_session() as session:
            sig_dict = dict(signal)
            if isinstance(sig_dict.get("take_profit"), (list, tuple)):
                sig_dict["take_profit"] = json.dumps(sig_dict["take_profit"])
            if isinstance(sig_dict.get("reasons"), (list, tuple)):
                sig_dict["reasons"] = json.dumps(sig_dict["reasons"])
            existing = session.get(SignalModel, sig_dict["signal_id"])
            if existing:
                for k, v in sig_dict.items():
                    setattr(existing, k, v)
            else:
                session.add(SignalModel(**sig_dict))
            session.commit()
            return sig_dict["signal_id"]

    def get_recent_signals(self, limit: int = 50) -> list[SignalModel]:
        with self._get_session() as session:
            stmt = select(SignalModel).order_by(SignalModel.created_at.desc()).limit(limit)
            return list(session.scalars(stmt).all())

    def get_signal(self, signal_id: str) -> SignalModel | None:
        with self._get_session() as session:
            return session.get(SignalModel, signal_id)

    # --- Prediction Repo ---
    def save_prediction(self, pred: dict[str, Any]) -> str:
        with self._get_session() as session:
            existing = session.get(PredictionModel, pred["prediction_id"])
            if existing:
                for k, v in pred.items():
                    setattr(existing, k, v)
            else:
                session.add(PredictionModel(**pred))
            session.commit()
            return pred["prediction_id"]

    def update_prediction_outcome(self, prediction_id: str, actual_outcome: str,
                                  actual_return_pct: float, is_correct: bool,
                                  simulated_pnl: float | None = None,
                                  transaction_costs: float | None = None,
                                  evaluation_notes: str | None = None) -> None:
        with self._get_session() as session:
            pred = session.get(PredictionModel, prediction_id)
            if pred:
                pred.actual_outcome = actual_outcome
                pred.actual_return_pct = actual_return_pct
                pred.is_correct = is_correct
                pred.simulated_pnl = simulated_pnl
                pred.transaction_costs = transaction_costs
                pred.evaluation_notes = evaluation_notes
                pred.eval_time = datetime.now(timezone.utc)
                session.commit()

    def get_unresolved_predictions(self) -> list[PredictionModel]:
        with self._get_session() as session:
            stmt = select(PredictionModel).where(PredictionModel.is_correct.is_(None))
            return list(session.scalars(stmt).all())

    def count_predictions(self) -> int:
        with self._get_session() as session:
            return int(session.scalar(select(func.count()).select_from(PredictionModel)) or 0)

    def get_predictions_history(self, limit: int = 500) -> list[PredictionModel]:
        with self._get_session() as session:
            stmt = select(PredictionModel).order_by(PredictionModel.created_at.desc()).limit(limit)
            return list(session.scalars(stmt).all())

    # --- Paper Orders & Positions ---
    def save_order(self, order: dict[str, Any]) -> str:
        with self._get_session() as session:
            allowed = {column.key for column in PaperOrderModel.__table__.columns}
            values = {key: value for key, value in order.items() if key in allowed}
            existing = session.get(PaperOrderModel, order["order_id"])
            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(PaperOrderModel(**values))
            session.commit()
            return order["order_id"]

    def get_open_orders(self, market: str | None = None) -> list[PaperOrderModel]:
        with self._get_session() as session:
            stmt = select(PaperOrderModel).where(PaperOrderModel.status.in_(["OPEN", "PARTIAL"]))
            if market:
                stmt = stmt.where(PaperOrderModel.market == market)
            return list(session.scalars(stmt).all())

    def save_position(self, pos: dict[str, Any]) -> str:
        with self._get_session() as session:
            allowed = {column.key for column in PaperPositionModel.__table__.columns}
            values = {key: value for key, value in pos.items() if key in allowed}
            existing = session.get(PaperPositionModel, pos["position_id"])
            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
            else:
                session.add(PaperPositionModel(**values))
            session.commit()
            return pos["position_id"]

    def get_open_positions(self, market: str | None = None) -> list[PaperPositionModel]:
        with self._get_session() as session:
            stmt = select(PaperPositionModel).where(PaperPositionModel.status == "OPEN")
            if market:
                stmt = stmt.where(PaperPositionModel.market == market)
            return list(session.scalars(stmt).all())

    def record_completed_trade(self, trade: dict[str, Any]) -> int:
        with self._get_session() as session:
            obj = TradeHistoryModel(**trade)
            session.add(obj)
            session.commit()
            return obj.id

    def get_trade_history(self, limit: int | None = 100) -> list[TradeHistoryModel]:
        with self._get_session() as session:
            stmt = select(TradeHistoryModel).order_by(TradeHistoryModel.closed_at.desc())
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    def save_trade_history(self, trade: dict[str, Any]) -> str:
        """Persist a completed trade and close its position in one transaction."""
        with self._get_session() as session:
            stmt = select(TradeHistoryModel).where(
                TradeHistoryModel.position_id == trade["position_id"]
            )
            existing = session.scalars(stmt).first()
            values = {
                "symbol": trade["symbol"],
                "market": trade["market"],
                "side": trade["side"],
                "entry_price": trade["entry_price"],
                "exit_price": trade["exit_price"],
                "amount": trade["amount"],
                "leverage": trade.get("leverage", 1.0),
                "pnl": trade["pnl"],
                "pnl_pct": trade["pnl_pct"],
                "fee": trade.get("fee", 0.0),
                "strategy": trade.get("strategy", "UNKNOWN"),
                "signal_id": trade.get("signal_id"),
                "opened_at": trade["opened_at"],
                "closed_at": trade["closed_at"],
                "close_reason": trade.get("close_reason", "UNKNOWN"),
            }
            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
            else:
                session.add(TradeHistoryModel(position_id=trade["position_id"], **values))
            position = session.get(PaperPositionModel, trade["position_id"])
            if position:
                position.status = "CLOSED"
                position.current_price = trade["exit_price"]
                position.close_price = trade["exit_price"]
                position.unrealized_pnl = 0.0
                position.realized_pnl = trade["pnl"]
                position.fees_paid = trade.get("fee", position.fees_paid)
                position.closed_at = trade["closed_at"]
            session.commit()
            return trade["position_id"]

    # --- Strategy Metrics & Models ---
    def update_strategy_metrics(self, strategy: str, market: str, win: bool, pnl: float) -> None:
        with self._get_session() as session:
            key = (strategy, market)
            m = session.get(StrategyMetricsModel, key)
            if not m:
                m = StrategyMetricsModel(strategy=strategy, market=market, total_signals=0,
                                         validated_signals=0, winning_trades=0, losing_trades=0,
                                         total_pnl=0.0, win_rate=0.0, profit_factor=1.0, weight=1.0)
                session.add(m)
            m.total_signals += 1
            m.validated_signals += 1
            if win:
                m.winning_trades += 1
            else:
                m.losing_trades += 1
            m.total_pnl += pnl
            total_resolved = m.winning_trades + m.losing_trades
            if total_resolved > 0:
                m.win_rate = m.winning_trades / total_resolved
            session.commit()

    def get_all_strategy_metrics(self) -> list[StrategyMetricsModel]:
        with self._get_session() as session:
            stmt = select(StrategyMetricsModel)
            return list(session.scalars(stmt).all())

    def get_strategy_weights(self) -> dict[str, float]:
        """Load persisted global adaptive strategy weights."""
        with self._get_session() as session:
            stmt = select(StrategyMetricsModel).where(StrategyMetricsModel.market == "ALL")
            return {row.strategy: float(row.weight) for row in session.scalars(stmt).all()}

    def save_strategy_weight(self, strategy: str, weight: float) -> None:
        """Persist the current adaptive weight independently of market metrics."""
        with self._get_session() as session:
            record = session.get(StrategyMetricsModel, (strategy, "ALL"))
            if record:
                record.weight = float(weight)
                record.last_updated = datetime.now(timezone.utc)
            else:
                session.add(StrategyMetricsModel(strategy=strategy, market="ALL", weight=float(weight)))
            session.commit()

    def save_model_registry(self, record: dict[str, Any]) -> str:
        with self._get_session() as session:
            rec_dict = dict(record)
            if isinstance(rec_dict.get("metrics"), dict):
                rec_dict["metrics"] = json.dumps(rec_dict["metrics"])
            existing = session.get(ModelRegistryModel, rec_dict["version"])
            if existing:
                for k, v in rec_dict.items():
                    setattr(existing, k, v)
            else:
                session.add(ModelRegistryModel(**rec_dict))
            session.commit()
            return rec_dict["version"]

    def get_active_model(self, model_type: str) -> ModelRegistryModel | None:
        with self._get_session() as session:
            stmt = (
                select(ModelRegistryModel)
                .where(ModelRegistryModel.model_type == model_type, ModelRegistryModel.is_active.is_(True))
                .order_by(ModelRegistryModel.trained_at.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()

    def promote_model(self, version: str) -> None:
        with self._get_session() as session:
            target = session.get(ModelRegistryModel, version)
            if not target:
                return
            # Deactivate others of same type
            session.execute(
                update(ModelRegistryModel)
                .where(ModelRegistryModel.model_type == target.model_type)
                .values(is_active=False)
            )
            target.is_active = True
            target.status = "PROMOTED"
            session.commit()

    def rollback_model(self, version: str) -> str | None:
        with self._get_session() as session:
            target = session.get(ModelRegistryModel, version)
            if not target:
                return None
            target.is_active = False
            target.status = "ROLLED_BACK"
            # Find previous validated
            prev_stmt = (
                select(ModelRegistryModel)
                .where(
                    ModelRegistryModel.model_type == target.model_type,
                    ModelRegistryModel.version != version,
                    ModelRegistryModel.status.in_(["VALIDATED", "PROMOTED"]),
                )
                .order_by(ModelRegistryModel.trained_at.desc())
                .limit(1)
            )
            prev = session.scalars(prev_stmt).first()
            if prev:
                prev.is_active = True
                prev.status = "PROMOTED"
                session.commit()
                return prev.version
            session.commit()
            return None

    # --- System Events & Notifications ---
    def save_simulator_state(self, state: dict[str, Any]) -> None:
        """Upsert the latest paper-account state for crash recovery."""
        with self._get_session() as session:
            record = session.get(SimulatorStateModel, "default")
            payload = json.dumps(state, default=lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value))
            if record:
                record.payload = payload
                record.updated_at = datetime.now(timezone.utc)
            else:
                session.add(SimulatorStateModel(state_id="default", payload=payload))
            session.commit()

    def get_simulator_state_record(self) -> tuple[dict[str, Any], datetime | None] | None:
        """Return a paper-account snapshot and its durable update timestamp."""
        with self._get_session() as session:
            record = session.get(SimulatorStateModel, "default")
            if not record:
                return None
            try:
                state = json.loads(record.payload)
            except (TypeError, json.JSONDecodeError):
                logger.exception("Stored simulator state is malformed")
                return None
            if not isinstance(state, dict):
                return None
            return state, record.updated_at

    def get_latest_account_record_timestamp(self) -> datetime | None:
        """Return the newest durable position, order, or trade record timestamp."""
        with self._get_session() as session:
            timestamps = [
                session.scalar(select(func.max(PaperPositionModel.opened_at))),
                session.scalar(select(func.max(PaperPositionModel.closed_at))),
                session.scalar(select(func.max(PaperOrderModel.updated_at))),
                session.scalar(select(func.max(TradeHistoryModel.closed_at))),
            ]
            present = [value for value in timestamps if value is not None]
            return max(present) if present else None

    def get_latest_account_event_timestamp(self) -> datetime | None:
        """Get the latest durable event that changes paper account state."""
        account_events = (
            "POSITION_OPENED", "POSITION_CLOSED", "ORDER_PLACED",
            "ORDER_FILLED", "TRADE_REJECTED",
        )
        with self._get_session() as session:
            return session.scalar(
                select(func.max(SystemEventModel.timestamp)).where(
                    SystemEventModel.event_type.in_(account_events)
                )
            )

    def get_simulator_state(self) -> dict[str, Any] | None:
        with self._get_session() as session:
            record = session.get(SimulatorStateModel, "default")
            if not record:
                return None
            try:
                state = json.loads(record.payload)
            except (TypeError, json.JSONDecodeError):
                logger.exception("Stored simulator state is malformed")
                return None
            return state if isinstance(state, dict) else None

    def save_system_event(self, event_dict: dict[str, Any]) -> str:
        with self._get_session() as session:
            ev = SystemEventModel(
                event_id=event_dict["event_id"],
                event_type=event_dict["event_type"],
                source=event_dict["source"],
                symbol=event_dict.get("symbol"),
                market=event_dict.get("market"),
                payload=json.dumps(
                    event_dict.get("payload", {}),
                    default=lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value),
                ),
            )
            session.add(ev)
            session.commit()
            return ev.event_id

    def save_notification(self, notif: dict[str, Any]) -> int:
        with self._get_session() as session:
            obj = NotificationModel(**notif)
            session.add(obj)
            session.commit()
            return obj.id

    def get_system_events(self, limit: int = 100) -> list:
        """Get recent system events."""
        with self._get_session() as session:
            from sqlalchemy import select
            from database.models import SystemEventModel
            stmt = (
                select(SystemEventModel)
                .order_by(SystemEventModel.timestamp.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def event_exists(self, event_id: str) -> bool:
        """Check if event exists in database."""
        with self._get_session() as session:
            from database.models import SystemEventModel
            return session.get(SystemEventModel, event_id) is not None

    def update_system_event_status(self, event_id: str, status: str) -> None:
        """Update system event status."""
        with self._get_session() as session:
            from database.models import SystemEventModel
            ev = session.get(SystemEventModel, event_id)
            if ev:
                # Update payload with status
                import json
                payload = json.loads(ev.payload)
                payload["status"] = status
                ev.payload = json.dumps(payload)
                session.commit()
