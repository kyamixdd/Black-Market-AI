"""Bridge between Orchestrator and FastAPI API."""
from __future__ import annotations

import logging
import asyncio
import json
import math
import re
import time
from datetime import datetime, timezone
from typing import Any

from core.orchestrator import Orchestrator
from core.event_bus import EventBus
from core.event_models import EventType
from database.repositories import Repository
from market.candle_manager import CandleManager

logger = logging.getLogger(__name__)


class OrchestratorBridge:
    """Bridge to access Orchestrator data for API endpoints."""

    def __init__(self, orchestrator: Orchestrator):
        self.orch = orchestrator
        self.repo: Repository = orchestrator.repo
        self.event_bus: EventBus = orchestrator.event_bus
        self.candles: CandleManager = orchestrator.candle_manager
        self.simulator = orchestrator.simulator
        self.intelligence = orchestrator.intelligence
        self.risk_manager = orchestrator.simulator.risk_manager
        self._candle_refresh_at: dict[tuple[str, str, str], float] = {}

    # ===== Market Data =====

    def get_market_snapshot(self, symbol: str, market: str) -> dict | None:
        """Get latest market snapshot for a symbol."""
        cached = self.orch.cache.get_snapshot(market, symbol)
        if cached and cached.get("price") is not None:
            return cached
        snap = self.repo.get_latest_snapshot(symbol, market)
        if not snap:
            return None
        return {
            "symbol": snap.symbol,
            "market": snap.market,
            "timestamp": snap.timestamp.isoformat() if snap.timestamp else None,
            "price": snap.price,
            "volume_24h": snap.volume_24h,
            "price_change_24h": snap.price_change_24h,
            "mark_price": snap.mark_price,
            "funding_rate": snap.funding_rate,
            "open_interest": snap.open_interest,
            "bid_ask_spread": snap.bid_ask_spread,
            "orderbook_imbalance": snap.orderbook_imbalance,
            "regime": snap.regime,
        }

    def get_all_market_snapshots(self) -> list[dict]:
        """Get all recent market snapshots."""
        snapshots: dict[tuple[str, str], dict] = {}
        for market in ("SPOT", "FUTURES"):
            for snapshot in self.orch.cache.get_market_tickers(market):
                snapshots[(market, snapshot["symbol"])] = snapshot
        for stored in self.repo.get_recent_snapshots(limit=1000):
            key = (stored.market, stored.symbol)
            if key not in snapshots:
                snapshots[key] = {
                    "symbol": stored.symbol,
                    "market": stored.market,
                    "timestamp": stored.timestamp,
                    "price": stored.price,
                    "volume_24h": stored.volume_24h,
                    "price_change_24h": stored.price_change_24h,
                    "mark_price": stored.mark_price,
                    "funding_rate": stored.funding_rate,
                    "open_interest": stored.open_interest,
                    "bid_ask_spread": stored.bid_ask_spread,
                    "orderbook_imbalance": stored.orderbook_imbalance,
                    "regime": stored.regime,
                }
        return list(snapshots.values())

    async def get_candles(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        limit: int = 200,
        end_time: int | None = None,
    ) -> list[dict]:
        """Fetch public Binance history and refresh the current candle at a bounded interval."""
        if end_time is not None:
            client = self.orch.spot_client if market == "SPOT" else self.orch.futures_client
            klines = await client.get_klines(
                symbol,
                timeframe,
                end_ms=end_time,
                limit=limit,
            )
            now_ms = int(time.time() * 1000)
            candles: dict[int, dict] = {}
            for row in klines:
                if len(row) < 7:
                    continue
                try:
                    open_time = int(row[0])
                    open_price = float(row[1])
                    high = float(row[2])
                    low = float(row[3])
                    close = float(row[4])
                    volume = float(row[5])
                    close_time = int(row[6])
                except (TypeError, ValueError, OverflowError):
                    logger.warning("Skipping malformed historical candle for %s %s", market, symbol)
                    continue
                if not all(math.isfinite(value) for value in (open_price, high, low, close, volume)):
                    continue
                if (
                    open_time >= end_time
                    or close_time > end_time
                    or close_time >= now_ms
                    or min(open_price, high, low, close, volume) < 0
                    or open_price == 0
                    or low == 0
                    or close == 0
                    or high < max(open_price, close, low)
                    or low > min(open_price, close)
                ):
                    continue
                candles[open_time] = {
                    "open_time": open_time,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "close_time": close_time,
                }
            return [candles[open_time] for open_time in sorted(candles)]

        key = (market, symbol, timeframe)
        now = time.monotonic()
        series = self.candles.get_series(market, symbol, timeframe, limit=1000)
        last_refresh = self._candle_refresh_at.get(key, 0.0)
        if not series or now - last_refresh >= 5:
            self._candle_refresh_at[key] = now
            await self.candles.collect_historical(
                self.orch.spot_client,
                self.orch.futures_client,
                market,
                symbol,
                timeframe,
                limit=max(500, limit),
            )
        return self.candles.get_series(market, symbol, timeframe, limit=limit)

    # ===== Signals =====

    def get_all_signals(self) -> list[dict]:
        """Return the latest persisted decision state for each signal."""
        latest: dict[str, dict] = {}
        for event in self.repo.get_system_events(limit=1000):
            if event.event_type not in {
                "SIGNAL_PROPOSED", "SIGNAL_VALIDATED", "SIGNAL_REJECTED", "SIGNAL_EXPIRED"
            }:
                continue
            try:
                payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
            except (TypeError, json.JSONDecodeError):
                logger.warning("Skipping malformed signal event %s", event.event_id)
                continue
            if not isinstance(payload, dict):
                continue
            # make_event stores envelope symbol/market outside the JSON payload.
            payload = {
                **payload,
                "symbol": event.symbol or payload.get("symbol"),
                "market": event.market or payload.get("market"),
            }
            signal_id = payload.get("signal_id") or event.event_id
            if signal_id in latest or not payload.get("symbol") or not payload.get("market"):
                continue
            signal = self._format_signal(payload)
            signal["status"] = event.event_type.removeprefix("SIGNAL_")
            signal["created_at"] = event.timestamp.isoformat() if event.timestamp else signal["created_at"]
            if event.timestamp:
                event_time = event.timestamp
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                signal["data_freshness"] = (
                    "LIVE" if (datetime.now(timezone.utc) - event_time).total_seconds() <= 300 else "STALE"
                )
            else:
                signal["data_freshness"] = "UNKNOWN"
            latest[signal_id] = signal
        return list(latest.values())

    def get_signals_by_market(self, market: str) -> list[dict]:
        """Get signals filtered by market."""
        return [s for s in self.get_all_signals() if s.get("market") == market]

    def get_signals_by_strategy(self, strategy: str) -> list[dict]:
        """Get signals filtered by strategy."""
        return [s for s in self.get_all_signals() if s.get("strategy") == strategy]

    def _format_signal(self, sig: dict) -> dict:
        """Format signal for API response."""
        take_profit = sig.get("take_profit", [])
        reasons = sig.get("reasons", [])
        if isinstance(take_profit, str):
            try:
                take_profit = json.loads(take_profit)
            except json.JSONDecodeError:
                take_profit = []
        if isinstance(reasons, str):
            try:
                reasons = json.loads(reasons)
            except json.JSONDecodeError:
                reasons = []
        return {
            "signal_id": sig.get("signal_id", ""),
            "symbol": sig.get("symbol", ""),
            "market": sig.get("market", ""),
            "strategy": sig.get("strategy", ""),
            "direction": sig.get("direction", ""),
            "timeframe": sig.get("timeframe", ""),
            "entry": sig.get("entry", 0.0),
            "stop_loss": sig.get("stop_loss", 0.0),
            "take_profit": take_profit if isinstance(take_profit, list) else [],
            "raw_score": sig.get("raw_score", 0.0),
            "confidence": sig.get("confidence", 0.0),
            "regime": sig.get("regime", "UNKNOWN"),
            "timeframe": sig.get("timeframe", ""),
            "reasons": reasons if isinstance(reasons, list) else [],
            "status": sig.get("status", "PROPOSED"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": "UNKNOWN",
            "weight": sig.get("_weight", 1.0),
        }

    # ===== Portfolio =====

    def get_portfolio_summary(self) -> dict:
        """Get portfolio summary."""
        sim = self.simulator
        spot_unrealized = sum(p.get("unrealized_pnl", 0) for p in sim.spot_positions.values())
        futures_unrealized = sum(p.get("unrealized_pnl", 0) for p in sim.futures_positions.values())
        spot_margin = sum(
            p.get("margin", p.get("entry_price", 0.0) * p.get("amount", 0.0))
            for p in sim.spot_positions.values()
        )
        futures_margin = sum(
            p.get("margin", p.get("entry_price", 0.0) * p.get("amount", 0.0))
            for p in sim.futures_positions.values()
        )
        spot_equity = sim.get_balance("SPOT") + spot_margin + spot_unrealized
        futures_equity = sim.get_balance("FUTURES") + futures_margin + futures_unrealized
        total = spot_equity + futures_equity
        now = datetime.now(timezone.utc)
        today = now.date()
        month = (now.year, now.month)
        closed_trades = self._all_closed_trades()
        realized = sum(t.get("pnl", 0) for t in closed_trades)
        daily_realized = 0.0
        monthly_realized = 0.0
        for trade in closed_trades:
            closed_at = trade.get("closed_at")
            if isinstance(closed_at, str):
                try:
                    closed_at = datetime.fromisoformat(closed_at)
                except ValueError:
                    continue
            if not isinstance(closed_at, datetime):
                continue
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=timezone.utc)
            closed_at = closed_at.astimezone(timezone.utc)
            if closed_at.date() == today:
                daily_realized += trade.get("pnl", 0)
            if (closed_at.year, closed_at.month) == month:
                monthly_realized += trade.get("pnl", 0)
        stats = self.get_trade_statistics()
        spot_baseline = sim.initial_spot_balance
        futures_baseline = sim.initial_futures_balance
        total_baseline = spot_baseline + futures_baseline
        spot_pnl = spot_equity - spot_baseline
        futures_pnl = futures_equity - futures_baseline
        total_pnl = total - total_baseline

        return {
            "spot_balance": spot_equity,
            "futures_balance": futures_equity,
            "total_balance": total,
            "spot_pnl": spot_pnl,
            "futures_pnl": futures_pnl,
            "total_pnl": total_pnl,
            "spot_return_pct": spot_pnl / spot_baseline * 100 if spot_baseline > 0 else 0.0,
            "futures_return_pct": futures_pnl / futures_baseline * 100 if futures_baseline > 0 else 0.0,
            "total_return_pct": total_pnl / total_baseline * 100 if total_baseline > 0 else 0.0,
            "daily_pnl": daily_realized,
            "monthly_pnl": monthly_realized,
            "realized_pnl": realized,
            "unrealized_pnl": spot_unrealized + futures_unrealized,
            "drawdown_pct": stats["max_drawdown_pct"],
        }

    # ===== Positions =====

    def get_open_positions(self) -> list[dict]:
        """Get all open positions."""
        positions = []
        for pos in self.simulator.spot_positions.values():
            positions.append(self._format_position(pos, "SPOT"))
        for pos in self.simulator.futures_positions.values():
            positions.append(self._format_position(pos, "FUTURES"))
        return positions

    def _format_position(self, pos: dict, market: str) -> dict:
        """Format position for API response."""
        liq_price = None
        margin_ratio = None
        if market == "FUTURES":
            from paper_trading.liquidation_engine import LiquidationEngine
            le = LiquidationEngine()
            liq_price = le.calculate_liquidation_price(pos)
            margin_ratio = le.get_margin_ratio(pos, pos.get("current_price", pos["entry_price"]))

        return {
            "position_id": pos["position_id"],
            "symbol": pos["symbol"],
            "market": market,
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "current_price": pos.get("current_price", pos["entry_price"]),
            "amount": pos["amount"],
            "leverage": pos.get("leverage", 1.0),
            "unrealized_pnl": pos.get("unrealized_pnl", 0.0),
            "realized_pnl": pos.get("realized_pnl", 0.0),
            "fees_paid": pos.get("fees_paid", 0.0),
            "stop_loss": pos.get("stop_loss"),
            "take_profit": pos.get("take_profit"),
            "liquidation_price": liq_price,
            "margin_ratio": margin_ratio,
            "status": pos.get("status", "OPEN"),
            "opened_at": pos["opened_at"].isoformat() if pos.get("opened_at") else None,
            "strategy": pos.get("strategy"),
        }

    # ===== Trades =====

    def get_recent_trades(self, limit: int = 100) -> list[dict]:
        """Get recent closed trades."""
        trades = self._all_closed_trades()[-limit:]
        return [
            {
                "position_id": t["position_id"],
                "symbol": t["symbol"],
                "market": t["market"],
                "side": t["side"],
                "entry_price": t["entry_price"],
                "exit_price": t["exit_price"],
                "amount": t["amount"],
                "leverage": t["leverage"],
                "pnl": t["pnl"],
                "pnl_pct": t["pnl_pct"],
                "fee": t["fee"],
                "strategy": t["strategy"],
                "opened_at": t["opened_at"].isoformat() if t.get("opened_at") else None,
                "closed_at": t["closed_at"].isoformat() if t.get("closed_at") else None,
                "close_reason": t["close_reason"],
            }
            for t in reversed(trades)
        ]

    def _all_closed_trades(self) -> list[dict]:
        """Merge persisted trades with the current simulator session without duplicates."""
        trades: dict[str, dict] = {}
        for item in self.repo.get_trade_history(limit=None):
            trades[item.position_id] = {
                "position_id": item.position_id,
                "symbol": item.symbol,
                "market": item.market,
                "side": item.side,
                "entry_price": item.entry_price,
                "exit_price": item.exit_price,
                "amount": item.amount,
                "leverage": item.leverage,
                "pnl": item.pnl,
                "pnl_pct": item.pnl_pct,
                "fee": item.fee,
                "strategy": item.strategy,
                "signal_id": item.signal_id,
                "opened_at": item.opened_at,
                "closed_at": item.closed_at,
                "close_reason": item.close_reason,
            }
        for trade in self.simulator.closed_trades:
            trades[trade["position_id"]] = trade

        def closed_timestamp(trade: dict) -> float:
            closed_at = trade.get("closed_at")
            if isinstance(closed_at, str):
                try:
                    closed_at = datetime.fromisoformat(closed_at)
                except ValueError:
                    return 0.0
            if not isinstance(closed_at, datetime):
                return 0.0
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=timezone.utc)
            return closed_at.timestamp()

        return sorted(
            trades.values(),
            key=closed_timestamp,
        )

    def get_trade_statistics(self) -> dict:
        """Get trade statistics."""
        trades = self._all_closed_trades()
        if not trades:
            return {
                "total": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
            }

        total_pnl = sum(t.get("pnl", 0) for t in trades)
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) < 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Max drawdown
        initial_equity = self.simulator.initial_spot_balance + self.simulator.initial_futures_balance
        peak = initial_equity
        equity = initial_equity
        max_dd = 0.0
        for t in trades:
            equity += t.get("pnl", 0)
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        return {
            "total": len(trades),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_dd,
        }

    # ===== Intelligence =====

    def get_strategy_metrics(self) -> list[dict]:
        """Get strategy performance metrics."""
        from database.repositories import Repository
        metrics = self.repo.get_all_strategy_metrics()
        return [
            {
                "strategy": m.strategy,
                "market": m.market,
                "total_signals": m.total_signals,
                "validated_signals": m.validated_signals,
                "winning_trades": m.winning_trades,
                "losing_trades": m.losing_trades,
                "win_rate": m.win_rate * 100,
                "total_pnl": m.total_pnl,
                "profit_factor": m.profit_factor,
                "weight": m.weight,
            }
            for m in metrics
        ]

    def get_strategy_weights(self) -> dict:
        """Get strategy weights by regime."""
        intel = self.orch.intelligence
        selector = intel.strategy_selector
        weights = {}
        for strat, weight in selector.weights.items():
            weights[strat] = {
                "base_weight": weight,
                "regime_adjusted": weight * selector.regime_prefs.get("BULL_TREND", {}).get(strat, 1.0) if "BULL_TREND" in selector.regime_prefs else weight,
            }
        return weights

    # ===== Learning =====

    def get_learning_status(self) -> dict:
        """Get learning engine status."""
        predictor = self.intelligence.predictor
        from database.repositories import Repository
        preds = self.repo.get_predictions_history(10000)
        resolved = [p for p in preds if p.is_correct is not None]
        correct = [p for p in resolved if p.is_correct]
        accuracy = len(correct) / len(resolved) * 100 if resolved else 0

        return {
            "model_status": "Ready" if predictor.is_trained else "Not Trained",
            "version": predictor.version if predictor.is_trained else None,
            "rf_loaded": predictor.rf_model is not None,
            "xgb_loaded": predictor.xgb_model is not None,
            "river_available": predictor.river_model is not None,
            "predictions_total": self.repo.count_predictions(),
            "predictions_resolved": len(resolved),
            "accuracy": accuracy,
            "recent_predictions": self.get_recent_predictions(10),
        }

    def get_recent_predictions(self, limit: int = 100) -> list[dict]:
        """Get recent predictions with outcomes."""
        from database.repositories import Repository
        preds = self.repo.get_predictions_history(limit)
        return [
            {
                "prediction_id": p.prediction_id,
                "symbol": p.symbol,
                "market": p.market,
                "timeframe": p.timeframe,
                "model_version": p.model_version,
                "strategy_version": p.strategy_version,
                "regime": p.regime,
                "horizon_minutes": p.horizon_minutes,
                "prob_up": p.prob_up,
                "prob_down": p.prob_down,
                "prob_flat": p.prob_flat,
                "predicted_class": p.predicted_class,
                "confidence": p.confidence,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "eval_time": p.eval_time.isoformat() if p.eval_time else None,
                "actual_outcome": p.actual_outcome,
                "actual_return_pct": p.actual_return_pct,
                "simulated_pnl": p.simulated_pnl,
                "transaction_costs": p.transaction_costs,
                "is_correct": p.is_correct,
                "evaluation_notes": p.evaluation_notes,
            }
            for p in preds
        ]

    def get_model_registry(self) -> list[dict]:
        """Get model registry."""
        from database.repositories import Repository
        models = self.repo.get_model_registry()
        return [
            {
                "version": m.version,
                "model_type": m.model_type,
                "trained_at": m.trained_at.isoformat() if m.trained_at else None,
                "metrics": m.metrics,
                "file_path": m.file_path,
                "status": m.status,
                "is_active": m.is_active,
                "is_champion": m.is_champion,
                "parent_version": m.parent_version,
                "evaluation_data": m.evaluation_data,
                "promotion_criteria": m.promotion_criteria,
                "rollback_checkpoint": m.rollback_checkpoint,
            }
            for m in models
        ]

    # ===== Risk =====

    def get_risk_metrics(self) -> dict:
        """Get current risk metrics."""
        sim = self.simulator
        manager = sim.risk_manager
        total_balance = sim._get_total_equity()

        # Current exposure
        total_risk = 0.0
        unmeasured_positions = 0
        for pos in sim.spot_positions.values():
            if pos.get("stop_loss"):
                risk = abs(pos["entry_price"] - pos["stop_loss"]) * pos["amount"]
                total_risk += risk
            else:
                unmeasured_positions += 1
        for pos in sim.futures_positions.values():
            if pos.get("stop_loss"):
                risk = abs(pos["entry_price"] - pos["stop_loss"]) * pos["amount"]
                total_risk += risk
            else:
                unmeasured_positions += 1

        exposure_pct = (total_risk / total_balance * 100) if total_balance > 0 else 0
        daily_loss_pct = abs(min(0, sim.get_daily_pnl())) / total_balance * 100 if total_balance > 0 else 0
        max_open_risk_pct = manager.max_open_risk_pct
        used_capacity_pct = min(100, exposure_pct / max_open_risk_pct * 100) if max_open_risk_pct > 0 else 0
        daily_capacity_pct = max(0, 100 * (1 - daily_loss_pct / manager.max_daily_loss_pct)) if manager.max_daily_loss_pct > 0 else 0
        if unmeasured_positions or daily_loss_pct >= manager.max_daily_loss_pct or exposure_pct >= max_open_risk_pct:
            status = "CRITICAL" if daily_loss_pct >= manager.max_daily_loss_pct else "WARNING"
        elif daily_loss_pct >= manager.max_daily_loss_pct * 0.75 or used_capacity_pct >= 75:
            status = "WARNING"
        else:
            status = "NORMAL"

        return {
            "current_exposure_pct": exposure_pct,
            "used_risk_capacity_pct": used_capacity_pct,
            "available_risk_capacity_pct": max(0, 100 - used_capacity_pct),
            "open_trade_risk_pct": exposure_pct,
            "daily_loss_capacity_pct": daily_capacity_pct,
            "risk_manager_status": status,
            "max_spot_positions": manager.max_spot_positions,
            "max_futures_positions": manager.max_futures_positions,
            "max_leverage": manager.max_leverage,
            "risk_per_trade_pct": manager.max_risk_pct,
            "max_daily_loss_pct": manager.max_daily_loss_pct,
            "max_total_open_pct": manager.max_open_risk_pct,
            "unmeasured_positions": unmeasured_positions,
        }

    # ===== Activity =====

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        """Get recent system events."""
        from database.repositories import Repository
        events = self.repo.get_system_events(limit=limit)
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "source": e.source,
                "symbol": e.symbol,
                "market": e.market,
                "payload": json.loads(e.payload) if isinstance(e.payload, str) else e.payload,
            }
            for e in events
        ]

    # ===== Settings =====

    def get_settings(self) -> dict:
        """Get current settings."""
        from config import (
            SPOT_ENABLED, USDM_FUTURES_ENABLED, SCAN_ALL_ELIGIBLE_SYMBOLS,
            TIMEFRAMES,
            TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
        )
        persisted = self.repo.get_app_settings()
        return {
            "spot_enabled": SPOT_ENABLED,
            "futures_enabled": USDM_FUTURES_ENABLED,
            "scan_all_eligible_symbols": SCAN_ALL_ELIGIBLE_SYMBOLS,
            "timeframes": TIMEFRAMES,
            "spot_initial_balance": self.simulator.initial_spot_balance,
            "futures_initial_balance": self.simulator.initial_futures_balance,
            "risk_per_trade_pct": self.risk_manager.max_risk_pct,
            "risk_max_daily_loss_pct": self.risk_manager.max_daily_loss_pct,
            "risk_max_total_open_pct": self.risk_manager.max_open_risk_pct,
            "risk_max_leverage": self.risk_manager.max_leverage,
            "max_spot_positions": self.risk_manager.max_spot_positions,
            "max_futures_positions": self.risk_manager.max_futures_positions,
            "telegram_enabled": TELEGRAM_ENABLED,
            "telegram_bot_token_configured": bool(TELEGRAM_BOT_TOKEN),
            "telegram_chat_id_configured": bool(TELEGRAM_CHAT_ID),
            "restart_required": [],
            **persisted,
        }

    def update_settings(self, updates: dict) -> dict:
        """Persist validated settings and apply safe risk/capital changes immediately."""
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

        if not updates:
            return self.get_settings()

        values = dict(updates)
        risk_fields = {
            "risk_per_trade_pct", "risk_max_daily_loss_pct",
            "risk_max_total_open_pct", "risk_max_leverage",
            "max_spot_positions", "max_futures_positions",
        }
        restart_fields = {
            "spot_enabled", "futures_enabled",
            "scan_all_eligible_symbols", "timeframes", "telegram_enabled",
        }
        restart_required = sorted(set(values) & restart_fields)

        # Validate the combined risk profile, not each submitted field in isolation.
        current = self.get_settings()
        effective = {**current, **values}
        if effective["risk_per_trade_pct"] > effective["risk_max_total_open_pct"]:
            raise ValueError("risk_per_trade_pct cannot exceed risk_max_total_open_pct")
        if not effective["spot_enabled"] and not effective["futures_enabled"]:
            raise ValueError("At least one market must remain enabled")
        if effective.get("telegram_enabled") and not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
            raise ValueError("Telegram cannot be enabled until its bot token and chat ID are configured securely")

        # Capital changes are only safe when there are no open positions or orders.
        capital_fields = {"spot_initial_balance", "futures_initial_balance"}
        if set(values) & capital_fields:
            has_open_positions = bool(self.simulator.spot_positions or self.simulator.futures_positions)
            has_open_orders = bool(self.simulator.open_orders)
            if has_open_positions or has_open_orders:
                raise ValueError("Virtual capital cannot be changed while positions or orders are open")
            if "spot_initial_balance" in values:
                delta = float(values["spot_initial_balance"]) - self.simulator.initial_spot_balance
                self.simulator.initial_spot_balance = float(values["spot_initial_balance"])
                self.simulator.spot_balance += delta
            if "futures_initial_balance" in values:
                delta = float(values["futures_initial_balance"]) - self.simulator.initial_futures_balance
                self.simulator.initial_futures_balance = float(values["futures_initial_balance"])
                self.simulator.futures_balance += delta

        risk = self.risk_manager
        mapping = {
            "risk_per_trade_pct": "max_risk_pct",
            "risk_max_daily_loss_pct": "max_daily_loss_pct",
            "risk_max_total_open_pct": "max_open_risk_pct",
            "risk_max_leverage": "max_leverage",
            "max_spot_positions": "max_spot_positions",
            "max_futures_positions": "max_futures_positions",
        }
        for setting, attribute in mapping.items():
            if setting in values:
                setattr(risk, attribute, values[setting])

        # Keep runtime values in sync with the UI and persist restart-required
        # choices for the next explicit restart.
        self.repo.save_app_settings(values)
        if set(values) & capital_fields:
            snapshot = self.simulator.get_state_snapshot()
            snapshot["closed_trades"] = []
            self.repo.save_simulator_state(snapshot)
        result = self.get_settings()
        result["restart_required"] = restart_required
        return result

    # ===== Health =====

    def get_system_health(self) -> dict:
        """Get system health status."""
        health = self.orch.health_monitor.get_status()
        return {
            "status": health.get("status", "unknown"),
            "components": health.get("components", {}),
            "metrics": health.get("metrics", {}),
            "uptime_seconds": health.get("metrics", {}).get("uptime_seconds", 0),
        }

    # ===== Market Heatmap =====

    def get_market_heatmap(self) -> list[dict]:
        """Return cached public tickers with cross-sectional relative strength and activity rank."""
        snapshots = [
            item for item in self.get_all_market_snapshots()
            if item.get("price") is not None
            and item.get("volume_24h") is not None
            and item.get("price_change_24h") is not None
        ]
        if not snapshots:
            return []
        average_change = sum(item["price_change_24h"] for item in snapshots) / len(snapshots)
        volumes = sorted(item["volume_24h"] for item in snapshots)
        result = []
        for item in snapshots:
            rank = sum(1 for volume in volumes if volume <= item["volume_24h"])
            result.append({
                "symbol": item["symbol"],
                "market": item["market"],
                "price_change_24h": item["price_change_24h"],
                "volume_24h": item["volume_24h"],
                "price": item["price"],
                "regime": item.get("regime") or "UNKNOWN",
                "relative_strength_pct": item["price_change_24h"] - average_change,
                "volume_rank_pct": rank / len(volumes) * 100,
                "volatility_24h_pct": None,
            })
        return sorted(result, key=lambda item: item["volume_24h"], reverse=True)

    # ===== Market Breadth =====

    def get_market_breadth(self) -> dict:
        """Get market breadth statistics."""
        snapshots = self.get_all_market_snapshots()
        snapshots = [s for s in snapshots if s.get("price_change_24h") is not None]
        advancing = sum(1 for s in snapshots if s["price_change_24h"] > 0)
        declining = sum(1 for s in snapshots if s["price_change_24h"] < 0)
        neutral = sum(1 for s in snapshots if s["price_change_24h"] == 0)
        total_volume = sum(s.get("volume_24h") or 0 for s in snapshots)
        spreads = [s["bid_ask_spread"] for s in snapshots if s.get("bid_ask_spread") is not None]
        imbalances = [s["orderbook_imbalance"] for s in snapshots if s.get("orderbook_imbalance") is not None]

        return {
            "advancing": advancing,
            "declining": declining,
            "neutral": neutral,
            "total_volume": total_volume,
            "avg_spread_bps": sum(spreads) / len(spreads) if spreads else None,
            "avg_orderbook_imbalance": sum(imbalances) / len(imbalances) if imbalances else None,
        }

    # ===== Volume =====

    async def get_volume_stats(self, symbol: str, market: str) -> dict:
        """Return measured aggressor-side quote volume for recent public aggregate trades."""
        client = self.orch.spot_client if market == "SPOT" else self.orch.futures_client
        trades, ticker = await asyncio.gather(
            client.get_aggregate_trades(symbol, limit=500),
            client.get_ticker_24h(symbol),
        )
        buy_volume = 0.0
        sell_volume = 0.0
        latest_trade_ms = None
        for trade in trades:
            price = float(trade["p"])
            quantity = float(trade["q"])
            quote_volume = price * quantity
            if trade.get("m") is True:
                sell_volume += quote_volume
            else:
                buy_volume += quote_volume
            latest_trade_ms = max(latest_trade_ms or 0, int(trade["T"]))
        return {
            "symbol": symbol,
            "market": market,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "total_volume": float(ticker["quoteVolume"]),
            "volume_change_24h": None,
            "buy_volume_7d_avg": None,
            "sell_volume_7d_avg": None,
            "flow_is_estimated": False,
            "flow_sample_size": len(trades),
            "flow_sample_scope": "Last 500 aggregate trades",
            "flow_last_trade_time": datetime.fromtimestamp(latest_trade_ms / 1000, tz=timezone.utc) if latest_trade_ms else None,
        }

    # ===== Long/Short =====

    async def get_long_short_stats(self, symbol: str) -> dict:
        """Return public USDⓈ-M account ratio, open interest, and mark funding."""
        ratio_rows, open_interest, mark = await asyncio.gather(
            self.orch.futures_client.get_global_long_short_account_ratio(symbol, period="1h", limit=24),
            self.orch.futures_client.get_open_interest(symbol),
            self.orch.futures_client.get_mark_price(symbol),
        )
        ratio = ratio_rows[-1] if ratio_rows else None
        if isinstance(mark, list):
            mark = next((row for row in mark if row.get("symbol") == symbol), None)
        mark = mark or {}
        long_short_ratio = float(ratio["longShortRatio"]) if ratio and ratio.get("longShortRatio") is not None else None
        long_volume = float(ratio["longAccount"]) * 100 if ratio and ratio.get("longAccount") is not None else None
        short_volume = float(ratio["shortAccount"]) * 100 if ratio and ratio.get("shortAccount") is not None else None
        if long_short_ratio is not None and (long_volume is None or short_volume is None):
            long_volume = long_short_ratio / (long_short_ratio + 1) * 100
            short_volume = 100 - long_volume
        mark_price = float(mark["markPrice"]) if mark.get("markPrice") is not None else None
        open_interest_contracts = float(open_interest["openInterest"]) if open_interest.get("openInterest") is not None else None
        return {
            "symbol": symbol,
            "long_short_ratio": long_short_ratio,
            "open_interest": open_interest_contracts * mark_price if open_interest_contracts is not None and mark_price is not None else None,
            "funding_rate": float(mark["lastFundingRate"]) if mark.get("lastFundingRate") is not None else None,
            "long_volume": long_volume,
            "short_volume": short_volume,
            "sample_period": "1h",
            "last_updated": datetime.fromtimestamp(float(ratio["timestamp"]) / 1000, tz=timezone.utc) if ratio and ratio.get("timestamp") else None,
            "history": [
                {
                    "timestamp": datetime.fromtimestamp(float(row["timestamp"]) / 1000, tz=timezone.utc),
                    "ratio": float(row["longShortRatio"]),
                }
                for row in ratio_rows
                if row.get("timestamp") is not None and row.get("longShortRatio") is not None
            ],
        }

    # ===== Market Data =====

    def get_all_markets(self) -> list[dict]:
        """Get all market snapshots."""
        return self.get_all_market_snapshots()

    def get_market_symbols(self) -> list[dict]:
        """Get all eligible symbols."""
        symbols = []
        for sym_info in self.orch.registry.list_symbols():
            snap = self.get_market_snapshot(sym_info["symbol"], sym_info["market"])
            if snap:
                symbols.append({
                    "symbol": sym_info["symbol"],
                    "market": sym_info["market"],
                    "base_asset": sym_info.get("base_asset", ""),
                    "quote_asset": sym_info.get("quote_asset", ""),
                    "price_precision": sym_info.get("price_precision", 4),
                    "quantity_precision": sym_info.get("quantity_precision", 4),
                    "tick_size": sym_info.get("tick_size", 0.0001),
                    "step_size": sym_info.get("step_size", 0.0001),
                    "min_notional": sym_info.get("min_notional", 10.0),
                    "status": sym_info.get("status", "TRADING"),
                    "is_eligible": sym_info.get("is_eligible", True),
                    "price": snap["price"],
                    "price_change_24h": snap["price_change_24h"],
                    "volume_24h": snap["volume_24h"],
                    "regime": snap["regime"],
                })
        return symbols


# Singleton instance
_bridge: OrchestratorBridge | None = None


def get_bridge(orchestrator: Orchestrator = None) -> OrchestratorBridge:
    """Get or create bridge instance."""
    global _bridge
    if orchestrator is not None:
        _bridge = OrchestratorBridge(orchestrator)
    return _bridge