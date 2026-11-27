"""Database repository classes for accessing and persisting intelligence data."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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
    TradeHistoryModel,
    SavedStrategyModel,
    BacktestReportModel,
    WorkspaceModel,
    PublicStrategyModel,
    PublicStrategyVersionModel,
    StrategyFavoriteModel,
    StrategyReportFlagModel,
    AssistantMemoryModel,
    AssistantFeedbackModel,
    AssistantPreferenceModel,
)

logger = logging.getLogger(__name__)


class Repository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    def _get_session(self) -> Session:
        return self._session_maker()

    # --- Symbol Repo ---
    def save_symbols(self, symbols: list[dict[str, Any]]) -> int:
        if not symbols:
            return 0
        now = datetime.now(timezone.utc)
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for item in symbols:
            key = (str(item["symbol"]), str(item["market"]))
            deduped[key] = {
                "symbol": key[0],
                "market": key[1],
                "base_asset": item["base_asset"],
                "quote_asset": item["quote_asset"],
                "price_precision": item.get("price_precision", 4),
                "quantity_precision": item.get("quantity_precision", 4),
                "tick_size": item.get("tick_size", 0.0001),
                "step_size": item.get("step_size", 0.0001),
                "min_notional": item.get("min_notional", 10.0),
                "status": item.get("status", "TRADING"),
                "is_eligible": item.get("is_eligible", True),
                "last_updated": item.get("last_updated", now),
            }
        rows = list(deduped.values())
        with self._get_session() as session:
            for idx in range(0, len(rows), 500):
                chunk = rows[idx:idx + 500]
                stmt = sqlite_insert(SymbolModel).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "market"],
                    set_={
                        "base_asset": stmt.excluded.base_asset,
                        "quote_asset": stmt.excluded.quote_asset,
                        "price_precision": stmt.excluded.price_precision,
                        "quantity_precision": stmt.excluded.quantity_precision,
                        "tick_size": stmt.excluded.tick_size,
                        "step_size": stmt.excluded.step_size,
                        "min_notional": stmt.excluded.min_notional,
                        "status": stmt.excluded.status,
                        "is_eligible": stmt.excluded.is_eligible,
                        "last_updated": stmt.excluded.last_updated,
                    },
                )
                session.execute(stmt)
            session.commit()
        return len(symbols)

    def get_eligible_symbols(self, market: str | None = None) -> list[SymbolModel]:
        with self._get_session() as session:
            stmt = select(SymbolModel).where(SymbolModel.is_eligible.is_(True))
            if market:
                stmt = stmt.where(SymbolModel.market == market)
            return list(session.scalars(stmt).all())

    # --- Candle Repo ---

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
    def save_candles(self, symbol: str, market: str, timeframe: str,
                     candles: list[dict[str, Any]]) -> int:
        """Upsert validated OHLC candles used by charting and outcome evaluation."""
        if not candles:
            return 0
        deduped: dict[int, dict[str, Any]] = {}
        for candle in candles:
            open_time = int(candle["open_time"])
            deduped[open_time] = {
                "symbol": symbol,
                "market": market,
                "timeframe": timeframe,
                "open_time": open_time,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "volume": float(candle.get("volume", 0.0)),
                "close_time": int(candle["close_time"]),
            }
        rows = list(deduped.values())
        with self._get_session() as session:
            for idx in range(0, len(rows), 500):
                chunk = rows[idx:idx + 500]
                stmt = sqlite_insert(CandleModel).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "market", "timeframe", "open_time"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                        "close_time": stmt.excluded.close_time,
                    },
                )
                session.execute(stmt)
            session.commit()
        return len(candles)

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

    def get_predictions_history(self, limit: int = 500) -> list[PredictionModel]:
        with self._get_session() as session:
            stmt = select(PredictionModel).order_by(PredictionModel.created_at.desc()).limit(limit)
            return list(session.scalars(stmt).all())

    # --- Paper Orders & Positions ---
    def save_order(self, order: dict[str, Any]) -> str:
        with self._get_session() as session:
            existing = session.get(PaperOrderModel, order["order_id"])
            if existing:
                for k, v in order.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(PaperOrderModel(**order))
            session.commit()
            return order["order_id"]

    def get_open_orders(self, market: str | None = None) -> list[PaperOrderModel]:
        with self._get_session() as session:
            stmt = select(PaperOrderModel).where(
                PaperOrderModel.status.in_(["OPEN", "PARTIAL", "FILLING", "RECOVERY_REVIEW"])
            )
            if market:
                stmt = stmt.where(PaperOrderModel.market == market)
            return list(session.scalars(stmt).all())

    def get_order_history(self, limit: int = 100, market: str | None = None) -> list[PaperOrderModel]:
        with self._get_session() as session:
            stmt = select(PaperOrderModel).order_by(PaperOrderModel.updated_at.desc()).limit(limit)
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
                "order_id": trade.get("order_id"),
                "opened_at": trade["opened_at"],
                "closed_at": trade["closed_at"],
                "close_reason": trade.get("close_reason", "UNKNOWN"),
                "max_favorable_excursion_pct": trade.get("max_favorable_excursion_pct", 0.0),
                "max_adverse_excursion_pct": trade.get("max_adverse_excursion_pct", 0.0),
                "prediction_correct": trade.get("prediction_correct"),
                "risk_calculation_verified": trade.get("risk_calculation_verified"),
                "calculation_audit_json": trade.get("calculation_audit_json"),
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

    def save_partial_trade(self, trade: dict[str, Any], position: dict[str, Any]) -> str:
        """Persist a partial execution and its remaining open position atomically."""
        with self._get_session() as session:
            session.add(TradeHistoryModel(
                position_id=trade["position_id"], symbol=trade["symbol"], market=trade["market"],
                side=trade["side"], entry_price=trade["entry_price"], exit_price=trade["exit_price"],
                amount=trade["amount"], leverage=trade.get("leverage", 1.0), pnl=trade["pnl"],
                pnl_pct=trade["pnl_pct"], fee=trade.get("fee", 0.0),
                strategy=trade.get("strategy", "UNKNOWN"), signal_id=trade.get("signal_id"),
                order_id=trade.get("order_id"), opened_at=trade["opened_at"],
                closed_at=trade["closed_at"], close_reason=trade.get("close_reason", "PARTIAL"),
            ))
            stored = session.get(PaperPositionModel, position["position_id"])
            if stored:
                stored.amount = position["amount"]
                stored.reserved_notional = position.get("reserved_notional", 0.0)
                stored.reserved_margin = position.get("reserved_margin", 0.0)
                stored.fees_paid = position.get("fees_paid", 0.0)
                stored.realized_pnl = position.get("realized_pnl", 0.0)
                stored.unrealized_pnl = position.get("unrealized_pnl", 0.0)
                stored.status = "OPEN"
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

    def get_model_registry(self) -> list[ModelRegistryModel]:
        """Return registered models in most recently trained order."""
        with self._get_session() as session:
            stmt = select(ModelRegistryModel).order_by(ModelRegistryModel.trained_at.desc())
            return list(session.scalars(stmt).all())

    @staticmethod
    def _has_complete_promotion_evidence(target: ModelRegistryModel) -> bool:
        """Only OOF, timestamp-purged, cost-aware gate evidence can authorize activation."""
        try:
            evidence_data = json.loads(target.evaluation_data or "{}")
            gate = evidence_data.get("promotion_gate") or {}
            provenance = gate.get("validation_provenance") or {}
            models = gate.get("models") or {}
            economics = gate.get("economic_evidence") or {}
            champions = gate.get("champion_evidence") or {}
            return (
                gate.get("passes") is True
                and provenance.get("method") == "purged_timestamp_walk_forward"
                and provenance.get("out_of_sample") is True
                and provenance.get("timestamps_required") is True
                and int(provenance.get("target_horizon_ms", 0)) > 0
                and int(provenance.get("purge_gap_ms", 0)) >= int(provenance.get("target_horizon_ms", 1))
                and int(provenance.get("rf_oof_count", 0)) > 0
                and int(provenance.get("xgb_oof_count", 0)) > 0
                and models.get("rf", {}).get("passes") is True
                and models.get("xgb", {}).get("passes") is True
                and economics.get("rf", {}).get("status") == "ok"
                and economics.get("xgb", {}).get("status") == "ok"
                and champions.get("rf", {}).get("status") == "ok"
                and champions.get("xgb", {}).get("status") == "ok"
                and target.status in {"CANDIDATE", "VALIDATED", "CHALLENGER"}
                and target.is_active is False
            )
        except (TypeError, ValueError, AttributeError):
            return False

    def promote_models(self, versions: list[str]) -> bool:
        """Atomically activate a set of model artifacts only with complete OOF evidence."""
        if not versions or len(set(versions)) != len(versions):
            return False
        with self._get_session() as session:
            targets = [session.get(ModelRegistryModel, version) for version in versions]
            if any(target is None for target in targets):
                return False
            targets = [target for target in targets if target is not None]
            if any(not self._has_complete_promotion_evidence(target) for target in targets):
                return False
            families = {target.model_type for target in targets}
            if len(families) != len(targets):
                return False
            for target in targets:
                session.execute(
                    update(ModelRegistryModel)
                    .where(ModelRegistryModel.model_type == target.model_type)
                    .values(is_active=False, is_champion=False)
                )
                target.is_active = True
                target.is_champion = True
                target.status = "CHAMPION"
            session.commit()
            return True

    def promote_model(self, version: str) -> bool:
        """Strict single-model promotion; unvalidated legacy/River records fail closed."""
        return self.promote_models([version])

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



    # --- Public strategy library ---
    @staticmethod
    def _public_strategy_dict(obj: PublicStrategyModel, *, favorite_count: int = 0,
                              is_favorite: bool = False, is_owner: bool = False) -> dict[str, Any]:
        return {
            "public_id": obj.public_id, "name": obj.name, "description": obj.description,
            "strategy_key": obj.strategy_key, "rules": json.loads(obj.rules_json),
            "supported_assets": json.loads(obj.assets_json),
            "supported_timeframes": json.loads(obj.timeframes_json),
            "risk_configuration": json.loads(obj.risk_json),
            "known_limitations": json.loads(obj.limitations_json),
            "backtest_report": json.loads(obj.report_json),
            "report_provenance": obj.report_provenance,
            "report_sha256": obj.report_sha256, "source_report_id": obj.source_report_id,
            "reproducibility_status": "NOT_REPLAYED", "verification_status": "NOT_VERIFIED",
            "version": obj.version, "favorite_count": favorite_count,
            "is_favorite": is_favorite, "is_owner": is_owner, "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        }

    def publish_public_strategy(self, record: dict[str, Any], owner_key: str) -> dict[str, Any]:
        from hashlib import sha256
        with self._get_session() as session:
            obj = session.get(PublicStrategyModel, record["public_id"])
            if obj is not None and obj.owner_key != owner_key:
                raise PermissionError("You cannot modify another user's published strategy.")
            version = (obj.version + 1) if obj else 1
            report = record.get("backtest_report", {})
            report_json = self._json_value(report)
            values = {
                "owner_key": owner_key, "name": record["name"], "description": record.get("description", ""),
                "strategy_key": record["strategy_key"], "rules_json": self._json_value(record["rules"]),
                "assets_json": self._json_value(record.get("supported_assets", [])),
                "timeframes_json": self._json_value(record.get("supported_timeframes", [])),
                "risk_json": self._json_value(record.get("risk_configuration", {})),
                "limitations_json": self._json_value(record.get("known_limitations", [])),
                "report_json": report_json, "report_sha256": sha256(report_json.encode("utf-8")).hexdigest(),
                "report_provenance": record.get("report_provenance", "USER_SUBMITTED"),
                "source_report_id": record.get("source_report_id"), "version": version, "visibility": "PUBLIC",
            }
            if obj is None:
                obj = PublicStrategyModel(public_id=record["public_id"], **values)
                session.add(obj)
            else:
                for key, value in values.items():
                    setattr(obj, key, value)
                obj.updated_at = datetime.now(timezone.utc)
            snapshot = {key: value for key, value in values.items() if key not in {"owner_key", "visibility"}}
            session.add(PublicStrategyVersionModel(
                version_id=uuid.uuid4().hex, public_id=obj.public_id, owner_key=owner_key,
                version=version, snapshot_json=self._json_value(snapshot),
            ))
            session.commit()
            return self._public_strategy_dict(obj)

    def list_public_strategies(self, *, query: str = "", strategy_key: str = "",
                               asset: str = "", timeframe: str = "", sort: str = "recent",
                               owner_key: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._get_session() as session:
            stmt = select(PublicStrategyModel).where(PublicStrategyModel.visibility == "PUBLIC")
            if query:
                needle = "%" + query.strip().lower().replace("%", "\\%").replace("_", "\\_") + "%"
                stmt = stmt.where(func.lower(PublicStrategyModel.name + " " + PublicStrategyModel.description).like(needle, escape="\\"))
            if strategy_key:
                stmt = stmt.where(PublicStrategyModel.strategy_key == strategy_key)
            if asset:
                stmt = stmt.where(func.lower(PublicStrategyModel.assets_json).like("%" + asset.lower() + "%"))
            if timeframe:
                stmt = stmt.where(func.lower(PublicStrategyModel.timeframes_json).like("%" + timeframe.lower() + "%"))
            if sort == "name":
                stmt = stmt.order_by(func.lower(PublicStrategyModel.name), PublicStrategyModel.created_at.desc())
            elif sort == "updated":
                stmt = stmt.order_by(PublicStrategyModel.updated_at.desc())
            else:
                stmt = stmt.order_by(PublicStrategyModel.created_at.desc())
            rows = list(session.scalars(stmt.offset(offset).limit(limit)).all())
            public_ids = [row.public_id for row in rows]
            favorite_counts: dict[str, int] = {}
            user_favorites: set[str] = set()
            if public_ids:
                counts_rows = session.execute(
                    select(StrategyFavoriteModel.public_id, func.count())
                    .where(StrategyFavoriteModel.public_id.in_(public_ids))
                    .group_by(StrategyFavoriteModel.public_id)
                ).all()
                favorite_counts = {str(pid): int(cnt) for pid, cnt in counts_rows}
                if owner_key:
                    user_favorites = set(
                        session.scalars(
                            select(StrategyFavoriteModel.public_id).where(
                                StrategyFavoriteModel.owner_key == owner_key,
                                StrategyFavoriteModel.public_id.in_(public_ids),
                            )
                        ).all()
                    )
            return [
                self._public_strategy_dict(
                    row,
                    favorite_count=favorite_counts.get(row.public_id, 0),
                    is_favorite=row.public_id in user_favorites,
                    is_owner=bool(owner_key and owner_key == row.owner_key),
                )
                for row in rows
            ]

    def get_public_strategy(self, public_id: str, owner_key: str | None = None) -> dict[str, Any] | None:
        with self._get_session() as session:
            obj = session.get(PublicStrategyModel, public_id)
            if obj is None or (obj.visibility != "PUBLIC" and obj.owner_key != owner_key):
                return None
            count = session.scalar(select(func.count()).select_from(StrategyFavoriteModel).where(StrategyFavoriteModel.public_id == public_id)) or 0
            fav = bool(owner_key and session.get(StrategyFavoriteModel, (owner_key, public_id)))
            result = self._public_strategy_dict(obj, favorite_count=count, is_favorite=fav, is_owner=bool(owner_key and owner_key == obj.owner_key))
            versions = session.scalars(select(PublicStrategyVersionModel).where(
                PublicStrategyVersionModel.public_id == public_id).order_by(PublicStrategyVersionModel.version.desc())).all()
            result["version_history"] = [{"version": v.version, "created_at": v.created_at.isoformat() if v.created_at else None,
                                          "snapshot": json.loads(v.snapshot_json)} for v in versions]
            return result

    def set_strategy_favorite(self, public_id: str, owner_key: str, favorite: bool) -> bool:
        with self._get_session() as session:
            strategy = session.get(PublicStrategyModel, public_id)
            if strategy is None or strategy.visibility != "PUBLIC":
                return False
            key = (owner_key, public_id)
            existing = session.get(StrategyFavoriteModel, key)
            if favorite and existing is None:
                session.add(StrategyFavoriteModel(owner_key=owner_key, public_id=public_id))
            elif not favorite and existing is not None:
                session.delete(existing)
            session.commit()
            return True

    def hide_public_strategy(self, public_id: str, owner_key: str) -> bool:
        with self._get_session() as session:
            obj = session.get(PublicStrategyModel, public_id)
            if obj is None or obj.owner_key != owner_key:
                return False
            obj.visibility = "PRIVATE"
            obj.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True

    def flag_public_strategy(self, public_id: str, reporter_key: str, reason: str, details: str = "") -> bool:
        with self._get_session() as session:
            obj = session.get(PublicStrategyModel, public_id)
            if obj is None or obj.visibility != "PUBLIC":
                return False
            session.add(StrategyReportFlagModel(flag_id=uuid.uuid4().hex, public_id=public_id,
                reporter_key=reporter_key, reason=reason, details=details[:1000], status="OPEN"))
            session.commit()
            return True

    def bind_community_owner(self, legacy_owner: str, authenticated_owner: str) -> None:
        """Bind pre-auth community records to the current authenticated owner key."""
        if not legacy_owner or legacy_owner == authenticated_owner:
            return
        with self._get_session() as session:
            session.execute(
                update(PublicStrategyModel)
                .where(PublicStrategyModel.owner_key == legacy_owner)
                .values(owner_key=authenticated_owner)
            )
            session.execute(
                update(PublicStrategyVersionModel)
                .where(PublicStrategyVersionModel.owner_key == legacy_owner)
                .values(owner_key=authenticated_owner)
            )
            session.execute(
                update(StrategyReportFlagModel)
                .where(StrategyReportFlagModel.reporter_key == legacy_owner)
                .values(reporter_key=authenticated_owner)
            )
            legacy_favorites = session.scalars(
                select(StrategyFavoriteModel).where(
                    StrategyFavoriteModel.owner_key == legacy_owner
                )
            ).all()
            for favorite in legacy_favorites:
                existing = session.get(
                    StrategyFavoriteModel,
                    (authenticated_owner, favorite.public_id),
                )
                if existing is not None:
                    session.delete(favorite)
                else:
                    favorite.owner_key = authenticated_owner
            session.commit()

    def list_strategy_favorites(self, owner_key: str) -> list[dict[str, Any]]:
        with self._get_session() as session:
            ids = session.scalars(select(StrategyFavoriteModel.public_id).where(
                StrategyFavoriteModel.owner_key == owner_key).order_by(StrategyFavoriteModel.created_at.desc())).all()
        output = []
        for public_id in ids:
            item = self.get_public_strategy(public_id, owner_key)
            if item is not None:
                output.append(item)
        return output

    # --- Saved strategies, backtest reports, and workspaces ---
    @staticmethod
    def _json_value(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}

    def save_strategy_definition(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._get_session() as session:
            obj = session.get(SavedStrategyModel, record["strategy_id"])
            values = {
                "name": record["name"],
                "strategy_key": record["strategy_key"],
                "description": record.get("description", ""),
                "definition_json": self._json_value(record.get("definition", {})),
                "tags_json": self._json_value(record.get("tags", [])),
                "version": int(record.get("version", 1)),
            }
            if obj is None:
                obj = SavedStrategyModel(strategy_id=record["strategy_id"], **values)
                session.add(obj)
            else:
                for key, value in values.items():
                    setattr(obj, key, value)
                obj.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._strategy_dict(obj)

    def get_strategy_definition(self, strategy_id: str) -> dict[str, Any] | None:
        with self._get_session() as session:
            obj = session.get(SavedStrategyModel, strategy_id)
            return self._strategy_dict(obj) if obj else None

    def list_strategy_definitions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._get_session() as session:
            rows = session.scalars(select(SavedStrategyModel).order_by(SavedStrategyModel.updated_at.desc()).limit(limit)).all()
            return [self._strategy_dict(row) for row in rows]

    def delete_strategy_definition(self, strategy_id: str) -> bool:
        with self._get_session() as session:
            obj = session.get(SavedStrategyModel, strategy_id)
            if obj is None:
                return False
            session.delete(obj)
            session.commit()
            return True

    def _strategy_dict(self, obj: SavedStrategyModel) -> dict[str, Any]:
        return {
            "strategy_id": obj.strategy_id, "name": obj.name, "strategy_key": obj.strategy_key,
            "description": obj.description, "definition": json.loads(obj.definition_json),
            "tags": json.loads(obj.tags_json), "version": obj.version,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        }

    def save_backtest_report(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._get_session() as session:
            obj = session.get(BacktestReportModel, record["report_id"])
            values = {
                "strategy_id": record.get("strategy_id"), "strategy_name": record["strategy_name"],
                "symbol": record["symbol"], "market": record["market"], "timeframe": record["timeframe"],
                "status": record.get("status", "saved"),
                "config_json": self._json_value(record.get("config", {})),
                "report_json": self._json_value(record.get("report", {})),
                "origin": record.get("origin", "USER_SUBMITTED"),
            }
            if obj is None:
                obj = BacktestReportModel(report_id=record["report_id"], **values)
                session.add(obj)
            else:
                for key, value in values.items():
                    setattr(obj, key, value)
            session.commit()
            return self._report_dict(obj)

    def get_backtest_report(self, report_id: str) -> dict[str, Any] | None:
        with self._get_session() as session:
            obj = session.get(BacktestReportModel, report_id)
            return self._report_dict(obj) if obj else None

    def list_backtest_reports(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._get_session() as session:
            rows = session.scalars(select(BacktestReportModel).order_by(BacktestReportModel.created_at.desc()).limit(limit)).all()
            return [self._report_dict(row) for row in rows]

    def delete_backtest_report(self, report_id: str) -> bool:
        with self._get_session() as session:
            obj = session.get(BacktestReportModel, report_id)
            if obj is None:
                return False
            session.delete(obj)
            session.commit()
            return True

    def _report_dict(self, obj: BacktestReportModel) -> dict[str, Any]:
        return {
            "report_id": obj.report_id, "strategy_id": obj.strategy_id, "strategy_name": obj.strategy_name,
            "symbol": obj.symbol, "market": obj.market, "timeframe": obj.timeframe, "status": obj.status,
            "config": json.loads(obj.config_json), "report": json.loads(obj.report_json), "origin": obj.origin,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
        }

    def save_workspace(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._get_session() as session:
            obj = session.get(WorkspaceModel, record["workspace_id"])
            values = {
                "name": record["name"], "owner_key": record.get("owner_key", "local"),
                "schema_version": int(record.get("schema_version", 1)),
                "payload_json": self._json_value(record.get("payload", {})),
            }
            if obj is None:
                obj = WorkspaceModel(workspace_id=record["workspace_id"], **values)
                session.add(obj)
            else:
                for key, value in values.items():
                    setattr(obj, key, value)
                obj.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._workspace_dict(obj)

    def get_workspace(self, workspace_id: str, owner_key: str = "local") -> dict[str, Any] | None:
        with self._get_session() as session:
            obj = session.get(WorkspaceModel, workspace_id)
            return self._workspace_dict(obj) if obj and obj.owner_key == owner_key else None

    def list_workspaces(self, owner_key: str = "local", limit: int = 100) -> list[dict[str, Any]]:
        with self._get_session() as session:
            rows = session.scalars(select(WorkspaceModel).where(WorkspaceModel.owner_key == owner_key).order_by(WorkspaceModel.updated_at.desc()).limit(limit)).all()
            return [self._workspace_dict(row) for row in rows]

    def delete_workspace(self, workspace_id: str, owner_key: str = "local") -> bool:
        with self._get_session() as session:
            obj = session.get(WorkspaceModel, workspace_id)
            if obj is None or obj.owner_key != owner_key:
                return False
            session.delete(obj)
            session.commit()
            return True

    def _workspace_dict(self, obj: WorkspaceModel) -> dict[str, Any]:
        return {
            "workspace_id": obj.workspace_id, "name": obj.name, "owner_key": obj.owner_key,
            "schema_version": obj.schema_version, "payload": json.loads(obj.payload_json),
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        }

    # --- System Events & Notifications ---
    def save_system_event(self, event_dict: dict[str, Any]) -> str:
        with self._get_session() as session:
            existing = session.get(SystemEventModel, event_dict["event_id"])
            payload_json = json.dumps(event_dict.get("payload", {}))
            if existing is None:
                ev = SystemEventModel(
                    event_id=event_dict["event_id"],
                    event_type=event_dict["event_type"],
                    source=event_dict["source"],
                    symbol=event_dict.get("symbol"),
                    market=event_dict.get("market"),
                    payload=payload_json,
                )
                session.add(ev)
                session.commit()
                return ev.event_id
            existing.event_type = event_dict["event_type"]
            existing.source = event_dict["source"]
            existing.symbol = event_dict.get("symbol")
            existing.market = event_dict.get("market")
            existing.payload = payload_json
            session.commit()
            return existing.event_id

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
                .where(SystemEventModel.event_type != "MARKET_DATA")
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

    # --- Assistant feedback and preference adaptation ---
    def save_assistant_feedback(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._get_session() as session:
            obj = AssistantFeedbackModel(**record)
            session.add(obj)
            session.commit()
            return {"feedback_id": obj.feedback_id, "request_id": obj.request_id,
                    "feedback_type": obj.feedback_type, "created_at": obj.created_at.isoformat()}

    def count_assistant_feedback(self, owner_key: str, feedback_type: str, *,
                                 preference_key: str | None = None) -> int:
        with self._get_session() as session:
            from datetime import timedelta
            stmt = select(func.count()).select_from(AssistantFeedbackModel).where(
                AssistantFeedbackModel.owner_key == owner_key,
                AssistantFeedbackModel.feedback_type == feedback_type,
                AssistantFeedbackModel.created_at >= datetime.now(timezone.utc) - timedelta(days=90),
            )
            if preference_key:
                stmt = stmt.where(AssistantFeedbackModel.correction == preference_key)
            return int(session.scalar(stmt) or 0)

    def get_assistant_preferences(self, owner_key: str) -> list[dict[str, Any]]:
        with self._get_session() as session:
            rows = list(session.scalars(select(AssistantPreferenceModel).where(
                AssistantPreferenceModel.owner_key == owner_key
            ).order_by(AssistantPreferenceModel.updated_at.desc())).all())
            return [{"preference_key": row.preference_key, "preference_value": row.preference_value,
                     "source": row.source, "evidence_count": row.evidence_count,
                     "confidence": row.confidence, "version": row.version,
                     "updated_at": row.updated_at.isoformat()} for row in rows]

    def set_assistant_preference(self, owner_key: str, preference_key: str,
                                 preference_value: str, *, source: str,
                                 evidence_count: int, confidence: float) -> dict[str, Any]:
        with self._get_session() as session:
            obj = session.get(AssistantPreferenceModel, (owner_key, preference_key))
            if obj is None:
                obj = AssistantPreferenceModel(owner_key=owner_key, preference_key=preference_key,
                    preference_value=preference_value, source=source, evidence_count=evidence_count,
                    confidence=confidence)
                session.add(obj)
            else:
                obj.preference_value = preference_value
                obj.source = source
                obj.evidence_count = evidence_count
                obj.confidence = confidence
                obj.version += 1
                obj.updated_at = datetime.now(timezone.utc)
            session.commit()
            return {"preference_key": obj.preference_key, "preference_value": obj.preference_value,
                    "source": obj.source, "evidence_count": obj.evidence_count,
                    "confidence": obj.confidence, "version": obj.version}

    def delete_assistant_preference(self, owner_key: str, preference_key: str) -> bool:
        with self._get_session() as session:
            obj = session.get(AssistantPreferenceModel, (owner_key, preference_key))
            if obj is None:
                return False
            session.delete(obj)
            session.commit()
            return True

    # --- Persistent assistant memory ---
    def save_assistant_memory(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._get_session() as session:
            existing = session.get(AssistantMemoryModel, record["memory_id"])
            if existing is None:
                existing = session.scalars(select(AssistantMemoryModel).where(
                    AssistantMemoryModel.owner_key == record["owner_key"],
                    AssistantMemoryModel.memory_type == record["memory_type"],
                    func.lower(AssistantMemoryModel.content) == str(record["content"]).strip().lower(),
                ).limit(1)).first()
            values = {
                "owner_key": record["owner_key"],
                "memory_type": record["memory_type"],
                "content": record["content"],
                "source": record.get("source", "user_explicit"),
                "importance": float(record.get("importance", 0.5)),
                "confidence": float(record.get("confidence", 1.0)),
                "tags_json": self._json_value(record.get("tags", [])),
                "expires_at": record.get("expires_at"),
            }
            if existing is not None:
                if existing.owner_key != record["owner_key"]:
                    raise PermissionError("Memory ownership mismatch.")
                for key, value in values.items():
                    setattr(existing, key, value)
                existing.version += 1
                existing.updated_at = datetime.now(timezone.utc)
                obj = existing
            else:
                obj = AssistantMemoryModel(memory_id=record["memory_id"], **values)
                session.add(obj)
            session.commit()
            return self._assistant_memory_dict(obj)

    def get_assistant_memory(self, memory_id: str, owner_key: str) -> dict[str, Any] | None:
        with self._get_session() as session:
            obj = session.get(AssistantMemoryModel, memory_id)
            if obj is None or obj.owner_key != owner_key:
                return None
            if obj.expires_at is not None and obj.expires_at.replace(tzinfo=None) <= datetime.now(timezone.utc).replace(tzinfo=None):
                session.delete(obj)
                session.commit()
                return None
            return self._assistant_memory_dict(obj)

    def retrieve_assistant_memories(self, owner_key: str, *, memory_types: list[str] | None = None,
                                    limit: int = 8) -> list[dict[str, Any]]:
        from sqlalchemy import or_
        now = datetime.now(timezone.utc)
        with self._get_session() as session:
            stmt = select(AssistantMemoryModel).where(
                AssistantMemoryModel.owner_key == owner_key,
                or_(AssistantMemoryModel.expires_at.is_(None), AssistantMemoryModel.expires_at > now),
            ).order_by(AssistantMemoryModel.importance.desc(), AssistantMemoryModel.updated_at.desc())
            if memory_types:
                stmt = stmt.where(AssistantMemoryModel.memory_type.in_(memory_types))
            rows = list(session.scalars(stmt.limit(max(1, min(int(limit), 200)))).all())
            for row in rows:
                row.access_count += 1
                row.last_accessed_at = now
            session.commit()
            return [self._assistant_memory_dict(row) for row in rows]

    def delete_assistant_memory(self, memory_id: str, owner_key: str) -> bool:
        with self._get_session() as session:
            obj = session.get(AssistantMemoryModel, memory_id)
            if obj is None or obj.owner_key != owner_key:
                return False
            session.delete(obj)
            session.commit()
            return True

    def delete_expired_assistant_memories(self, *, now: datetime | None = None) -> int:
        from sqlalchemy import delete
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is not None:
            current = current.replace(tzinfo=None)
        with self._get_session() as session:
            result = session.execute(delete(AssistantMemoryModel).where(
                AssistantMemoryModel.expires_at.is_not(None),
                AssistantMemoryModel.expires_at <= current,
            ))
            session.commit()
            return int(result.rowcount or 0)

    @staticmethod
    def _assistant_memory_dict(obj: AssistantMemoryModel) -> dict[str, Any]:
        return {
            "memory_id": obj.memory_id,
            "memory_type": obj.memory_type,
            "content": obj.content,
            "source": obj.source,
            "importance": obj.importance,
            "confidence": obj.confidence,
            "tags": json.loads(obj.tags_json),
            "version": obj.version,
            "access_count": obj.access_count,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
            "last_accessed_at": obj.last_accessed_at.isoformat() if obj.last_accessed_at else None,
            "expires_at": obj.expires_at.isoformat() if obj.expires_at else None,
        }
