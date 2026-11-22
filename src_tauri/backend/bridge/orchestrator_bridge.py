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
from market.analytics import breadth_summary, historical_volatility, volume_comparison, price_change, return_correlation

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
        self._analytics_cache: dict[tuple[str, str], tuple[float, dict]] = {}


    def get_market_data_status(self) -> dict:
        """Expose a stable aggregate market-data health contract."""
        markets = {market: self.orch.cache.get_data_status(market)
                  for market in ("SPOT", "FUTURES")}
        scanner = getattr(self.orch, "scanner", None)
        websocket = getattr(scanner, "websocket_manager", None)
        stream_status = websocket.status_snapshot() if websocket is not None else {
            "state": "UNAVAILABLE", "last_message_ms": None,
            "message_age_ms": None, "reconnect_attempts": 0, "active_streams": 0}
        return {"markets": markets, "websocket": stream_status,
                "checked_at": datetime.now(timezone.utc).isoformat()}

    # ===== Market Data =====

    def get_market_snapshot(self, symbol: str, market: str) -> dict | None:
        """Get latest market snapshot for a symbol."""
        cached = self.orch.cache.get_snapshot(market, symbol)
        if cached and cached.get("price") is not None:
            enriched = self._with_freshness(cached)
            volatility, atr = self._volatility_metrics(market, symbol)
            enriched["volatility_24h_pct"] = volatility
            enriched["atr_24h_pct"] = atr
            return enriched
        snap = self.repo.get_latest_snapshot(symbol, market)
        if not snap:
            return None
        return self._with_freshness({
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
        })

    @staticmethod
    def _with_freshness(snapshot: dict) -> dict:
        timestamp = snapshot.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = None
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            age = max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds())
            freshness = "LIVE" if age <= 90 else "DELAYED" if age <= 300 else "STALE"
        else:
            age, freshness = None, "UNKNOWN"
        return {**snapshot, "data_age_seconds": age, "data_freshness": freshness}

    def get_all_market_snapshots(self) -> list[dict]:
        """Get all recent market snapshots with computed 1h-candle risk analytics."""
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
        result = []
        for item in snapshots.values():
            enriched = self._with_freshness(item)
            volatility = item.get("volatility_24h_pct")
            atr = item.get("atr_24h_pct")
            enriched["volatility_24h_pct"] = volatility
            enriched["atr_24h_pct"] = atr
            result.append(enriched)
        return result

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

    async def get_symbol_analytics(self, symbol: str, market: str, timeframe: str = "1h") -> dict:
        """Return interval changes and indicators with explicit candle requirements."""
        candles = await self.get_candles(symbol, market, timeframe, limit=200)
        closes, volumes = [], []
        highs, lows = [], []
        now_ms = int(time.time() * 1000)
        for row in candles:
            try:
                if int(row["close_time"]) >= now_ms:
                    continue
                close, volume = float(row["close"]), float(row["volume"])
                high, low = float(row["high"]), float(row["low"])
                if not all(math.isfinite(value) for value in (close, volume, high, low)) or min(close, high, low) <= 0 or volume < 0:
                    continue
                closes.append(close); volumes.append(volume); highs.append(high); lows.append(low)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        changes = {
            "1h": price_change(closes, 1),
            "24h": price_change(closes, 24),
            "7d": price_change(closes, 168),
        }
        vol = historical_volatility(closes, 24)
        volume_stats = volume_comparison(volumes, 20)
        atr_pct = None
        if len(closes) >= 15:
            tr = [max(highs[index] - lows[index],
                       abs(highs[index] - closes[index - 1]),
                       abs(lows[index] - closes[index - 1]))
                  for index in range(1, len(closes))]
            atr_pct = sum(tr[-14:]) / 14 / closes[-1] * 100
        return {
            "symbol": symbol, "market": market, "timeframe": timeframe,
            "price_change_pct": changes,
            "historical_volatility_24h_pct": vol,
            "atr_14_pct": atr_pct,
            "volume_vs_prior_20_candles": volume_stats,
            "completed_candle_count": len(closes),
            "required_candles": {"1h_change": 2, "24h_change": 25, "7d_change": 169,
                                 "historical_volatility_24h": 25, "atr_14": 15,
                                 "volume_comparison": 21},
            "data_completeness": {
                **{key: "READY" if value is not None else "INSUFFICIENT_DATA"
                   for key, value in changes.items()},
                "historical_volatility_24h": "READY" if vol is not None else "INSUFFICIENT_DATA",
                "atr_14": "READY" if atr_pct is not None else "INSUFFICIENT_DATA",
                "volume_comparison": volume_stats["status"],
            },
        }

    async def get_asset_correlation(self, left_symbol: str, right_symbol: str,
                                    market: str, timeframe: str = "1h",
                                    limit: int = 200) -> dict:
        """Calculate aligned close-return correlation for two selected assets."""
        left_rows, right_rows = await asyncio.gather(
            self.get_candles(left_symbol, market, timeframe, limit=limit),
            self.get_candles(right_symbol, market, timeframe, limit=limit),
        )
        now_ms = int(time.time() * 1000)
        def completed_closes(rows):
            result = {}
            for row in rows:
                try:
                    if int(row["close_time"]) >= now_ms:
                        continue
                    value = float(row["close"])
                    if value > 0 and math.isfinite(value):
                        result[int(row["open_time"])] = value
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
            return result
        left, right = completed_closes(left_rows), completed_closes(right_rows)
        common = sorted(set(left) & set(right))
        value = return_correlation([left[key] for key in common],
                                   [right[key] for key in common], minimum_returns=20)
        return {
            "symbol_a": left_symbol, "symbol_b": right_symbol, "market": market,
            "timeframe": timeframe, "correlation": value,
            "aligned_candle_count": len(common), "return_sample_count": max(0, len(common) - 1),
            "status": "READY" if value is not None else "INSUFFICIENT_DATA",
            "method": "Pearson correlation of aligned close-to-close logarithmic returns",
        }

    # ===== Signals =====

    def get_all_signals(self) -> list[dict]:
        """Get persisted signal decisions from the local event history."""
        signals = []
        for event in self.repo.get_system_events(limit=1000):
            if event.event_type not in {"SIGNAL_PROPOSED", "SIGNAL_VALIDATED", "SIGNAL_REJECTED", "SIGNAL_EXPIRED"}:
                continue
            try:
                payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
            except json.JSONDecodeError:
                logger.warning("Skipping malformed signal event %s", event.event_id)
                continue
            if not isinstance(payload, dict) or not payload.get("symbol"):
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
            signals.append(signal)
        return signals

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
        account_builder = getattr(sim, "get_account_equity_breakdown", None)
        if callable(account_builder):
            account = account_builder()
        else:
            # Backward-compatible path for lightweight simulator adapters and
            # test doubles that expose balances/positions but not the new helper.
            spot_unrealized = sum(
                float(p.get("unrealized_pnl", 0.0) or 0.0)
                for p in getattr(sim, "spot_positions", {}).values()
            )
            futures_unrealized = sum(
                float(p.get("unrealized_pnl", 0.0) or 0.0)
                for p in getattr(sim, "futures_positions", {}).values()
            )
            spot_available = float(sim.get_balance("SPOT"))
            futures_available = float(sim.get_balance("FUTURES"))
            account = {
                "spot_available_balance": spot_available,
                "futures_available_balance": futures_available,
                "total_available_balance": spot_available + futures_available,
                "spot_used_capital": 0.0,
                "futures_used_margin": 0.0,
                "total_used_margin": 0.0,
                "total_used_capital": 0.0,
                "spot_unrealized_pnl": spot_unrealized,
                "futures_unrealized_pnl": futures_unrealized,
                "spot_equity": spot_available + spot_unrealized,
                "futures_equity": futures_available + futures_unrealized,
                "total_equity": spot_available + futures_available
                + spot_unrealized + futures_unrealized,
            }
        spot_unrealized = account["spot_unrealized_pnl"]
        futures_unrealized = account["futures_unrealized_pnl"]
        spot_equity = account["spot_equity"]
        futures_equity = account["futures_equity"]
        total = account["total_equity"]
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
            "spot_available_balance": account["spot_available_balance"],
            "futures_available_balance": account["futures_available_balance"],
            "total_available_balance": account["total_available_balance"],
            "spot_used_capital": account["spot_used_capital"],
            "futures_used_margin": account["futures_used_margin"],
            "total_used_margin": account["total_used_margin"],
            "total_used_capital": account["total_used_capital"],
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
        preds = self.repo.get_predictions_history(10000)
        resolved = [p for p in preds if p.is_correct is not None]
        correct = [p for p in resolved if p.is_correct]
        accuracy = len(correct) / len(resolved) * 100 if resolved else 0
        learning_service = getattr(self.orch, "learning_service", None)
        state = getattr(learning_service, "state", "waiting")

        return {
            "model_status": "Trained" if predictor.is_trained else "Training" if state in {"bootstrapping", "training"} else "Not Trained",
            "version": predictor.version if predictor.is_trained else None,
            "rf_loaded": predictor.rf_model is not None,
            "xgb_loaded": predictor.xgb_model is not None,
            "river_available": predictor.river_model is not None,
            "predictions_total": len(preds),
            "predictions_resolved": len(resolved),
            "accuracy": accuracy,
            "recent_predictions": self.get_recent_predictions(10),
            "training_state": state,
            "training_samples": getattr(learning_service, "training_samples", 0),
            "last_training_at": getattr(learning_service, "last_training_at", None),
            "last_cycle_status": getattr(learning_service, "last_cycle_status", "waiting"),
            "river_updates": getattr(learning_service, "river_updates", 0),
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
        models = self.repo.get_model_registry()
        def decode(value):
            if not value:
                return None
            if isinstance(value, dict):
                return value
            try:
                return json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return {}
        return [
            {
                "version": m.version,
                "model_type": m.model_type,
                "trained_at": m.trained_at.isoformat() if m.trained_at else None,
                "metrics": decode(m.metrics) or {},
                "file_path": m.file_path,
                "status": m.status,
                "is_active": m.is_active,
                "is_champion": m.is_champion,
                "parent_version": m.parent_version,
                "evaluation_data": decode(m.evaluation_data),
                "promotion_criteria": decode(m.promotion_criteria),
                "rollback_checkpoint": m.rollback_checkpoint,
            }
            for m in models
        ]

    # ===== Risk =====

    def get_risk_metrics(self) -> dict:
        """Get current risk metrics."""
        sim = self.simulator
        manager = sim.risk_manager
        account = sim.get_account_equity_breakdown()
        total_balance = account["total_equity"]
        daily_pnl = sim.get_daily_pnl()
        daily_baseline = sim.get_daily_equity_baseline()

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
        daily_loss_pct = abs(min(0, daily_pnl)) / daily_baseline * 100 if daily_baseline > 0 else 0
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
        """Return effective runtime settings without exposing secret values."""
        from config import (
            SPOT_ENABLED, USDM_FUTURES_ENABLED, SCAN_ALL_ELIGIBLE_SYMBOLS,
            TIMEFRAMES, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
        )
        orchestrator = getattr(self, "orch", None)
        saved = getattr(orchestrator, "_runtime_settings", {})
        return {
            "spot_enabled": saved.get("spot_enabled", getattr(getattr(orchestrator, "_discovery", None), "spot_enabled", SPOT_ENABLED)),
            "futures_enabled": saved.get("futures_enabled", USDM_FUTURES_ENABLED),
            "scan_all_eligible_symbols": saved.get("scan_all_eligible_symbols", SCAN_ALL_ELIGIBLE_SYMBOLS),
            "timeframes": saved.get("timeframes", TIMEFRAMES),
            "spot_initial_balance": self.simulator.initial_spot_balance,
            "futures_initial_balance": self.simulator.initial_futures_balance,
            "risk_per_trade_pct": self.risk_manager.max_risk_pct,
            "risk_max_daily_loss_pct": self.risk_manager.max_daily_loss_pct,
            "risk_max_total_open_pct": self.risk_manager.max_open_risk_pct,
            "risk_max_leverage": self.risk_manager.max_leverage,
            "max_spot_positions": self.risk_manager.max_spot_positions,
            "max_futures_positions": self.risk_manager.max_futures_positions,
            "telegram_enabled": saved.get("telegram_enabled", getattr(orchestrator, "telegram", None) is not None),
            "telegram_bot_token_configured": bool(TELEGRAM_BOT_TOKEN),
            "telegram_chat_id_configured": bool(TELEGRAM_CHAT_ID),
        }

    def update_settings(self, updates: dict) -> dict:
        """Persist and apply settings to the live orchestrator."""
        self.orch.apply_runtime_settings(updates, persist=True)
        return self.get_settings()

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

    def _volatility_metrics(self, market: str, symbol: str) -> tuple[float | None, float | None]:
        """Return 24 hourly-return realized volatility and 14-period ATR as price percentages."""
        get_series = getattr(getattr(self, "candles", None), "get_series", None)
        if not callable(get_series):
            return None, None
        rows = get_series(market, symbol, "1h", limit=26)
        now_ms = int(time.time() * 1000)
        completed = []
        for row in rows:
            try:
                values = [float(row[key]) for key in ("open", "high", "low", "close", "volume")]
                open_time, close_time = int(row["open_time"]), int(row["close_time"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if (not all(math.isfinite(value) for value in values) or min(values[:4]) <= 0
                    or values[4] < 0 or values[1] < max(values[0], values[3], values[2])
                    or values[2] > min(values[0], values[3]) or close_time >= now_ms):
                continue
            completed.append(row)
        completed = sorted({int(row["open_time"]): row for row in completed}.values(),
                           key=lambda row: int(row["open_time"]))
        closes = [float(row["close"]) for row in completed]
        realized = historical_volatility(closes, window=24) if len(closes) >= 25 else None
        atr_pct = None
        if len(completed) >= 15:
            ranges = []
            for index in range(1, len(completed)):
                row, previous = completed[index], completed[index - 1]
                high, low, prev_close = float(row["high"]), float(row["low"]), float(previous["close"])
                ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
            last_close = closes[-1]
            if last_close > 0 and ranges:
                atr_pct = sum(ranges[-14:]) / min(14, len(ranges)) / last_close * 100.0
        return realized, atr_pct

    def get_market_heatmap(self) -> list[dict]:
        """Return ticker heatmap with market-scoped relative strength and measured volatility."""
        snapshots = [item for item in self.get_all_market_snapshots()
                     if item.get("price") is not None and item.get("volume_24h") is not None
                     and item.get("price_change_24h") is not None]
        if not snapshots:
            return []
        benchmark_by_market: dict[str, list[float]] = {}
        for item in snapshots:
            benchmark_by_market.setdefault(item["market"], []).append(float(item["price_change_24h"]))
        average_by_market = {
            market: sum(changes) / len(changes) for market, changes in benchmark_by_market.items() if changes
        }
        volumes = sorted(float(item["volume_24h"]) for item in snapshots)
        result = []
        for item in snapshots:
            volatility, atr = self._volatility_metrics(item["market"], item["symbol"])
            market_sample = len(benchmark_by_market.get(item["market"], []))
            rank = sum(1 for volume in volumes if volume <= float(item["volume_24h"]))
            result.append({
                "symbol": item["symbol"], "market": item["market"],
                "price_change_24h": item["price_change_24h"], "volume_24h": item["volume_24h"],
                "price": item["price"], "regime": item.get("regime") or "UNKNOWN",
                "relative_strength_pct": float(item["price_change_24h"]) - average_by_market[item["market"]],
                "relative_strength_benchmark": "mean 24h change of cached eligible tickers in same market",
                "relative_strength_sample_size": market_sample,
                "volume_rank_pct": rank / len(volumes) * 100,
                "volatility_24h_pct": volatility, "atr_24h_pct": atr,
                "data_age_seconds": item.get("data_age_seconds"),
                "data_freshness": item.get("data_freshness", "UNKNOWN"),
            })
        return sorted(result, key=lambda item: item["volume_24h"], reverse=True)

    # ===== Market Breadth =====

    def get_market_breadth(self) -> dict:
        """Return breadth by market to avoid conflating duplicate SPOT/FUTURES symbols."""
        snapshots = self.get_all_market_snapshots()
        by_market = {}
        for market in ("SPOT", "FUTURES"):
            valid = [item for item in snapshots if item.get("market") == market
                     and item.get("price_change_24h") is not None
                     and math.isfinite(float(item["price_change_24h"]))]
            summary = breadth_summary(float(item["price_change_24h"]) for item in valid)
            volume_values = [float(item["volume_24h"]) for item in valid
                             if item.get("volume_24h") is not None
                             and math.isfinite(float(item["volume_24h"])) and float(item["volume_24h"]) >= 0]
            by_market[market] = {
                **summary, "total_quote_volume_24h": sum(volume_values) if volume_values else None,
                "sample_coverage": len(valid),
            }
        total_sample = sum(item["sample_coverage"] for item in by_market.values())
        return {
            "markets": by_market, "sample_size": total_sample,
            "scope": "cached eligible market tickers; SPOT and FUTURES counts are separate market listings",
            "total_quote_volume_24h": sum(
                item["total_quote_volume_24h"] or 0 for item in by_market.values()
            ) if total_sample else None,
            "avg_spread_bps": None, "avg_orderbook_imbalance": None,
            "spread_status": "UNAVAILABLE: no live order-book depth sample",
            "orderbook_status": "UNAVAILABLE: no live order-book depth sample",
        }

    # ===== Volume =====

    async def get_volume_stats(self, symbol: str, market: str) -> dict:
        """Return sampled aggressor flow plus completed daily quote-volume comparisons."""
        client = self.orch.spot_client if market == "SPOT" else self.orch.futures_client
        cache_key, now = (market, symbol), time.monotonic()
        cached = self._analytics_cache.get(cache_key)
        if cached and now - cached[0] < 60:
            result = dict(cached[1])
            age = max(0.0, now - cached[0])
            result["data_age_seconds"] = age
            result["data_freshness"] = "LIVE" if age <= 90 else "DELAYED" if age <= 300 else "STALE"
            return result
        trades, ticker, daily = await asyncio.gather(
            client.get_aggregate_trades(symbol, limit=500),
            client.get_ticker_24h(symbol),
            client.get_klines(symbol, "1d", limit=8),
        )
        buy_volume = sell_volume = 0.0
        latest_trade_ms = None
        for trade in trades:
            price, quantity = float(trade["p"]), float(trade["q"])
            if not math.isfinite(price * quantity) or price <= 0 or quantity < 0:
                continue
            if trade.get("m") is True:
                sell_volume += price * quantity
            else:
                buy_volume += price * quantity
            latest_trade_ms = max(latest_trade_ms or 0, int(trade["T"]))
        now_ms, completed = int(time.time() * 1000), []
        for row in daily:
            if len(row) < 8:
                continue
            try:
                close_time, quote_volume = int(row[6]), float(row[7])
            except (TypeError, ValueError, OverflowError):
                continue
            if close_time < now_ms and math.isfinite(quote_volume) and quote_volume >= 0:
                completed.append((close_time, quote_volume))
        completed.sort()
        values = [value for _, value in completed]
        baseline = values[-7:] if len(values) >= 7 else []
        avg_daily = sum(baseline) / 7 if len(baseline) == 7 else None
        current_24h = float(ticker["quoteVolume"])
        change = ((current_24h / avg_daily) - 1) * 100 if avg_daily and avg_daily > 0 else None
        result = {
            "symbol": symbol, "market": market, "buy_volume": buy_volume, "sell_volume": sell_volume,
            "total_volume": current_24h, "volume_change_24h": None,
            "buy_volume_7d_avg": None, "sell_volume_7d_avg": None,
            "average_daily_quote_volume_7d": avg_daily, "volume_change_vs_7d_avg_pct": change,
            "daily_baseline_count": len(baseline), "daily_baseline_status": "READY" if len(baseline) == 7 else "INSUFFICIENT_DATA",
            "comparison_period": "Current rolling 24h vs mean of 7 completed UTC daily candles",
            "data_timestamp": datetime.now(timezone.utc), "data_age_seconds": 0.0, "data_freshness": "LIVE",
            "flow_is_estimated": False, "flow_sample_size": len(trades),
            "flow_sample_scope": "Last 500 aggregate trades; not full 24h",
            "flow_last_trade_time": datetime.fromtimestamp(latest_trade_ms / 1000, tz=timezone.utc) if latest_trade_ms else None,
        }
        self._analytics_cache[cache_key] = (now, result)
        return dict(result)

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
