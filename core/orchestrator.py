"""Main orchestrator: coordinates all services and the intelligence bus."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import uuid
from typing import Any

import numpy as np

from config import (
    PAPER_TRADING_ENABLED,
    SPOT_ENABLED,
    TELEGRAM_ENABLED,
    USDM_FUTURES_ENABLED,
    PREDICTION_HORIZON_MINUTES,
    TIMEFRAMES,
    MAX_CONCURRENT_SCANS,
    MAX_STREAMS_PER_CONNECTION,
)
from core.event_bus import EventBus
from core.disaster_recovery import create_disaster_recovery_orchestrator
from core.event_models import EventType, make_event
from database.connection import Database
from database.repositories import Repository
from exchange.futures_client import FuturesClient
from exchange.market_discovery import MarketDiscovery
from exchange.rate_limiter import RateLimiter
from exchange.spot_client import SpotClient
from exchange.symbol_registry import SymbolRegistry
from exchange.websocket_manager import WebSocketManager
from intelligence.decision_engine import DecisionEngine
from intelligence.feature_engine import FeatureEngine
from intelligence.intelligence_core import IntelligenceCore
from intelligence.strategy_selector import StrategySelector
from learning.predictor import Predictor
from learning.performance_analyzer import PerformanceAnalyzer
from learning.outcome_labeler import OutcomeLabeler
from learning.trainer import LearningOrchestrator
from market.candle_manager import CandleManager
from market.data_integrity import DataIntegrityGuardian
from market.market_cache import MarketCache
from market.scanner import Scanner
from notifications.telegram_client import TelegramClient
from paper_trading.simulator import Simulator
from core.health_monitor import HealthMonitor

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, db: Database):
        self.db: Database = db
        self.repo: Repository = Repository(db.session_maker())
        self.event_bus: EventBus = EventBus()
        self.rate_limiter: RateLimiter = RateLimiter()
        self.registry: SymbolRegistry = SymbolRegistry()
        self.cache: MarketCache = MarketCache()
        self.spot_client: SpotClient = SpotClient(self.rate_limiter)
        self.futures_client: FuturesClient = FuturesClient(self.rate_limiter)
        self.ws_manager: WebSocketManager = WebSocketManager(self.rate_limiter, max_streams_per_conn=MAX_STREAMS_PER_CONNECTION)
        self.ws_manager.add_handler(self._on_exchange_ws_message)
        self.candle_manager: CandleManager = CandleManager()
        self.scanner: Scanner = Scanner(self.event_bus, self.registry, self.cache,
                                       self.spot_client, self.futures_client)
        self.decision_engine: DecisionEngine = DecisionEngine(self.event_bus)
        self.strategy_selector: StrategySelector = StrategySelector()
        self.feature_engine: FeatureEngine = FeatureEngine()
        self.predictor: Predictor = Predictor()
        self.simulator: Simulator = Simulator(self.event_bus)
        self.telegram: TelegramClient | None = TelegramClient() if TELEGRAM_ENABLED else None
        # Data integrity
        self.integrity: DataIntegrityGuardian = DataIntegrityGuardian(self.candle_manager)
        # Intelligence core
        self.intelligence: IntelligenceCore = IntelligenceCore(self.event_bus, self.candle_manager, self.integrity)
        # Keep one shared model/feature engine for inference and scheduled training.
        self.intelligence.predictor = self.predictor
        self.intelligence.feature_engine = self.feature_engine
        self.intelligence.strategy_selector = self.strategy_selector
        self.learning_orchestrator = LearningOrchestrator(self.repo, self.predictor)
        self._last_prediction_candle: dict[str, int] = {}
        # Learning accountability
        self.outcome_labeler = OutcomeLabeler(self.repo, self.simulator)
        self.performance_analyzer = PerformanceAnalyzer(self.repo)
        self.health_monitor: HealthMonitor = HealthMonitor()
        self._running: bool = False
        self._tasks: list[asyncio.Task] = []
        self._event_bus_task: asyncio.Task | None = None
        self._analysis_cursors: dict[str, int] = {"SPOT": 0, "FUTURES": 0}
        self._analysis_batch_size = 5
        self._analysis_timeframes = tuple(TIMEFRAMES)
        self._discovery: MarketDiscovery = MarketDiscovery(self.registry, self.rate_limiter,
                                                        SPOT_ENABLED, USDM_FUTURES_ENABLED)
        # State tracking for dashboard
        self._scanning: bool = False
        self._ws_connected: bool = False
        self._tracked_symbols: list[str] = []
        self._recent_snapshots: list[dict] = []
        self._current_regime: str = "UNKNOWN"
        self.disaster_recovery = create_disaster_recovery_orchestrator(
            db=self.db,
            simulator=self.simulator,
            ws_manager=self.ws_manager,
            spot_client=self.spot_client,
            futures_client=self.futures_client,
            symbol_registry=self.registry,
            candle_manager=self.candle_manager,
            telegram_client=self.telegram,
            persist_state=self._persist_state,
            reconnect_callback=self.ws_manager.restart,
        )

    async def initialize(self) -> None:
        logger.info("Initializing BlackMarket AI...")
        # Load symbols from DB
        saved = self.repo.get_eligible_symbols()
        for s in saved:
            self.registry.register(s.symbol, s.market, {
                "base_asset": s.base_asset, "quote_asset": s.quote_asset,
                "price_precision": s.price_precision, "quantity_precision": s.quantity_precision,
                "tick_size": s.tick_size, "step_size": s.step_size,
                "min_notional": s.min_notional, "status": s.status,
                "is_eligible": s.is_eligible,
            })
        logger.info("Loaded %d symbols from DB", len(saved))
        # Discover fresh market universe
        result = await self._discovery.discover_all()
        logger.info("Discovered: spot=%d, futures=%d", result["spot"], result["futures"])
        # Persist symbols
        self.repo.save_symbols(self.registry.to_dicts())
        # Setup event persistence (critical events to SQLite for recovery)
        self.event_bus.set_persist(self._persist_event)
        # Setup event subscriptions
        self._setup_subscriptions()
        # Recover positions once, then start backups, watchdog, and reconnect management.
        await self.disaster_recovery.start()
        # Prefer the exact simulator snapshot (balances, margin, pending orders,
        # and daily P&L) over reconstructing account state from trades alone.
        saved_state = self.repo.get_simulator_state()
        if saved_state:
            self.simulator.restore_state(saved_state)
            logger.info("Restored persisted simulator snapshot")
        logger.info("Initialization complete")

    def _setup_subscriptions(self) -> None:
        # Signal validation
        self.event_bus.subscribe(EventType.SIGNAL_PROPOSED, self._on_signal_proposed)
        # Paper execution
        self.event_bus.subscribe(EventType.SIGNAL_VALIDATED, self._on_signal_validated)
        self.event_bus.subscribe(EventType.SIGNAL_REJECTED, self._on_signal_rejected)
        self.event_bus.subscribe(EventType.SIGNAL_EXPIRED, self._on_signal_expired)
        # Market data for price updates
        self.event_bus.subscribe(EventType.MARKET_DATA, self._on_market_data)
        # Learning feedback
        self.event_bus.subscribe(EventType.POSITION_CLOSED, self._on_position_closed)
        # Position opened
        self.event_bus.subscribe(EventType.POSITION_OPENED, self._on_position_opened)
        self.event_bus.subscribe(EventType.ORDER_PLACED, self._on_order_placed)
        self.event_bus.subscribe(EventType.ORDER_FILLED, self._on_order_filled)
        self.event_bus.subscribe(EventType.TRADE_REJECTED, self._on_trade_rejected)
        # Risk alerts
        self.event_bus.subscribe(EventType.RISK_ALERT, self._on_risk_alert)
        # System health
        self.event_bus.subscribe(EventType.SYSTEM_HEALTH, self._on_system_health)
        # Model events
        self.event_bus.subscribe(EventType.MODEL_TRAINED, self._on_model_trained)
        self.event_bus.subscribe(EventType.MODEL_PROMOTED, self._on_model_promoted)
        self.event_bus.subscribe(EventType.MODEL_ROLLED_BACK, self._on_model_rolled_back)

    def _event_signal(self, event) -> dict[str, Any]:
        """Rehydrate event envelope fields consumed by make_event()."""
        return {**event.payload, "symbol": event.symbol, "market": event.market}

    async def _send_telegram(self, method, *args, **kwargs) -> bool:
        """Send once and enqueue transient failures for background retry."""
        if not self.telegram:
            return False
        try:
            delivered = bool(await method(*args, **kwargs))
        except Exception:
            logger.exception("Telegram notification failed")
            delivered = False
        if not delivered and self.disaster_recovery.telegram_retry:
            notification_id = f"{getattr(method, '__name__', 'telegram')}-{uuid.uuid4().hex}"
            self.disaster_recovery.telegram_retry.queue_notification(
                notification_id, method, *args, **kwargs
            )
        return delivered

    async def _on_signal_proposed(self, event) -> None:
        await self.decision_engine.evaluate_signal(self._event_signal(event))

    async def _on_signal_validated(self, event) -> None:
        if not PAPER_TRADING_ENABLED:
            return
        signal = self._event_signal(event)
        strategy = signal.get("strategy")
        regime = signal.get("regime")
        signal["_weight"] = self.strategy_selector.get_weight(strategy, regime)
        await self.simulator.execute_signal(signal)

        if self.telegram and signal.get("confidence", 0) >= 0.75:
            await self._send_telegram(self.telegram.send_strong_setup, signal)

    async def _on_signal_rejected(self, event) -> None:
        if self.telegram:
            await self._send_telegram(self.telegram.send_signal_update, self._event_signal(event), "rejected")

    async def _on_signal_expired(self, event) -> None:
        if self.telegram:
            await self._send_telegram(self.telegram.send_signal_update, self._event_signal(event), "expired")

    async def _on_exchange_ws_message(self, message: dict[str, Any]) -> None:
        """Convert Binance combined ticker streams into normal market-data events."""
        data = message.get("data", message) if isinstance(message, dict) else {}
        if not isinstance(data, dict) or data.get("e") != "24hrTicker":
            return
        symbol = data.get("s")
        market = message.get("_market", "SPOT")
        try:
            price = float(data.get("c", 0))
            volume = float(data.get("q", 0))
            change = float(data.get("P", 0))
        except (TypeError, ValueError, OverflowError):
            return
        if not symbol or not all(math.isfinite(value) for value in (price, volume, change)) or price <= 0:
            return
        self._ws_connected = True
        self._last_ws_message_at = asyncio.get_running_loop().time()
        self.cache.update_ticker(market, symbol, price, volume, change)
        await self.event_bus.publish(make_event(
            EventType.MARKET_DATA,
            "binance_websocket",
            symbol=symbol,
            market=market,
            price=price,
            volume_24h=volume,
            price_change_24h=change,
        ))

    async def _start_market_websockets(self) -> None:
        """Subscribe to the most liquid eligible symbols; REST still covers the full universe."""
        spot_streams: list[str] = []
        futures_streams: list[str] = []
        for market, enabled, target in (
            ("SPOT", SPOT_ENABLED, spot_streams),
            ("FUTURES", USDM_FUTURES_ENABLED, futures_streams),
        ):
            if not enabled:
                continue
            tickers = self.cache.get_market_tickers(market)
            tickers.sort(key=lambda item: float(item.get("volume_24h") or 0.0), reverse=True)
            target.extend(
                f"{item['symbol'].lower()}@ticker"
                for item in tickers[:100]
                if item.get("symbol")
            )
        await self.ws_manager.start(spot_streams, futures_streams)
        logger.info(
            "Exchange WebSocket subscriptions started: spot=%d futures=%d",
            len(spot_streams), len(futures_streams),
        )

    async def _on_market_data(self, event) -> None:
        payload = event.payload
        market = event.market or payload.get("market", "SPOT")
        symbol = event.symbol or payload.get("symbol")
        price = payload.get("price")
        if price is None and symbol:
            price = self.cache.get_price(market, symbol)
        mark_price = payload.get("mark_price")
        funding_rate = payload.get("funding_rate")
        volume_24h = payload.get("volume_24h")
        if symbol and isinstance(volume_24h, (int, float)) and volume_24h >= 0:
            self.simulator.update_market_volume(market, symbol, float(volume_24h))
        if symbol and isinstance(price, (int, float)) and price > 0:
            await self.simulator.update_prices(
                market,
                symbol,
                float(price),
                mark_price=float(mark_price) if isinstance(mark_price, (int, float)) and mark_price > 0 else None,
                funding_rate=float(funding_rate) if isinstance(funding_rate, (int, float)) else None,
            )
            await self.simulator.check_limit_orders(market, symbol, float(price))

    async def _on_position_closed(self, event) -> None:
        # Learning feedback: evaluate prediction if any
        trade = event.payload.get("trade")
        if trade:
            self.repo.save_trade_history(trade)
            strategy = trade.get("strategy")
            if strategy:
                won = trade.get("pnl", 0.0) > 0
                self.strategy_selector.update_performance(
                    strategy, won, trade.get("pnl_pct", 0.0)
                )
                self.repo.update_strategy_metrics(
                    strategy, trade.get("market", "SPOT"), won, trade.get("pnl", 0.0)
                )
            await self._persist_state()
            if self.telegram:
                await self._send_telegram(self.telegram.send_position_closed, trade)

    async def _on_position_opened(self, event) -> None:
        position = event.payload.get("position")
        if position:
            self.repo.save_position(position)
            await self._persist_state()
            if self.telegram:
                await self._send_telegram(self.telegram.send_position_opened, position)

    async def _on_order_placed(self, event) -> None:
        self._persist_paper_order(event.payload.get("order"))
        await self._persist_state()

    async def _on_order_filled(self, event) -> None:
        self._persist_paper_order(event.payload.get("order"))
        await self._persist_state()

    async def _on_trade_rejected(self, event) -> None:
        order = event.payload.get("order")
        if order:
            self._persist_paper_order(order)
            await self._persist_state()

    def _persist_paper_order(self, order: dict[str, Any] | None) -> None:
        if not order:
            return
        self.repo.save_order({
            "order_id": order["order_id"],
            "signal_id": order.get("signal_id"),
            "symbol": order["symbol"],
            "market": order["market"],
            "order_type": order["order_type"],
            "side": order["side"],
            "amount": order["amount"],
            "price": order.get("entry_price", order.get("price")),
            "stop_loss": order.get("stop_loss"),
            "take_profit": order.get("take_profit"),
            "status": order["status"],
            "filled_amount": order.get("filled_amount", 0.0),
            "avg_fill_price": order.get("avg_fill_price", 0.0),
            "fee": order.get("fee", 0.0),
            "leverage": order.get("leverage", 1.0),
            "created_at": order.get("created_at"),
        })

    async def _on_risk_alert(self, event) -> None:
        payload = event.payload
        alert_type = payload.get("alert_type", "UNKNOWN")
        if self.telegram and alert_type in ("DAILY_LOSS", "MARGIN_RISK", "LIQUIDATION"):
            if alert_type == "DAILY_LOSS":
                await self._send_telegram(self.telegram.send_daily_risk_warning, 
                    self.simulator.get_daily_pnl(),
                    self.simulator._get_total_equity()
                )
            elif alert_type == "MARGIN_RISK":
                await self._send_telegram(self.telegram.send_early_warning, 
                    f"Margin risk: {payload.get('message', '')}",
                    event.symbol or "", event.market or ""
                )
            elif alert_type == "LIQUIDATION":
                await self._send_telegram(self.telegram.send_early_warning, 
                    f"LIQUIDATION: {payload.get('message', '')}",
                    event.symbol or "", event.market or ""
                )

    async def _on_system_health(self, event) -> None:
        if self.telegram:
            payload = event.payload
            await self._send_telegram(self.telegram.send_connection_status, 
                payload.get("component", "SYSTEM"),
                payload.get("status", "unknown"),
                payload.get("message", "")
            )

    async def _on_model_trained(self, event) -> None:
        if self.telegram:
            await self._send_telegram(self.telegram.send_learning_report, event.payload)

    async def _on_model_promoted(self, event) -> None:
        if self.telegram:
            await self._send_telegram(self.telegram.send_message, f"🚀 <b>MODEL PROMOTED</b>\n\nVersion: {event.payload.get('version', 'unknown')}")

    async def _on_model_rolled_back(self, event) -> None:
        if self.telegram:
            await self._send_telegram(self.telegram.send_message, f"↩️ <b>MODEL ROLLED BACK</b>\n\nVersion: {event.payload.get('version', 'unknown')}")

    async def _persist_event(self, event) -> None:
        """Persist critical events to SQLite for state recovery after interruptions."""
        # High-volume ticker events are transient and must not grow the SQLite
        # event journal without bound. Persist decisions, fills, risk, and lifecycle events.
        if event.event_type in {EventType.MARKET_DATA, EventType.MARKET_SNAPSHOT}:
            return
        try:
            event_dict = {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "source": event.source,
                "symbol": event.symbol,
                "market": event.market,
                "payload": event.payload,
            }
            self.repo.save_system_event(event_dict)
        except Exception as exc:
            logger.error("Failed to persist event %s: %s", event.event_id, exc)

    async def run(self) -> None:
        self._running = True
        # The event bus must have a consumer before scanners publish prices,
        # signals, fills, or risk events.
        self._event_bus_task = asyncio.create_task(self.event_bus.run(), name="blackmarket-event-bus")
        await self.scanner.start()
        # Give the initial REST scan a moment to populate the ticker cache before
        # selecting high-liquidity WebSocket subscriptions.
        for _ in range(10):
            if (SPOT_ENABLED and self.cache.get_market_tickers("SPOT")) or (
                USDM_FUTURES_ENABLED and self.cache.get_market_tickers("FUTURES")
            ):
                break
            await asyncio.sleep(1)
        await self._start_market_websockets()
        self._tasks.append(asyncio.create_task(self._analysis_loop(), name="blackmarket-analysis"))
        self._tasks.append(asyncio.create_task(self._learning_loop(), name="blackmarket-learning"))
        logger.info("BlackMarket AI running")
        # Main loop - keep running until stopped
        while self._running:
            await asyncio.sleep(60)
            # Periodic persistence; watchdog heartbeats come from successful analysis cycles.
            await self._persist_state()

    async def _analysis_loop(self) -> None:
        """Rotate through the complete eligible universe and run real strategy analysis.

        Ticker discovery covers every eligible symbol. Candle-heavy analysis is
        deliberately batched to respect public exchange rate limits on a desktop PC.
        """
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCANS)

        async def analyze_one(market: str, symbol: str) -> None:
            async with semaphore:
                try:
                    for timeframe in self._analysis_timeframes:
                        updated_count = await self.candle_manager.collect_historical(
                            self.spot_client,
                            self.futures_client,
                            market,
                            symbol,
                            timeframe,
                            limit=200,
                        )
                        candles = self.candle_manager.get_series(
                            market, symbol, timeframe, limit=200
                        )
                        if candles:
                            # Persist the full history once, then only the newest
                            # candles on subsequent refreshes to avoid repeated DB writes.
                            candles_to_save = candles if updated_count > 1 else candles[-2:]
                            self.repo.save_candles([
                                {
                                    "symbol": symbol,
                                    "market": market,
                                    "timeframe": timeframe,
                                    "open_time": candle["open_time"],
                                    "open": candle["open"],
                                    "high": candle["high"],
                                    "low": candle["low"],
                                    "close": candle["close"],
                                    "volume": candle["volume"],
                                    "close_time": candle["close_time"],
                                }
                                for candle in candles_to_save
                            ])
                    signals = await self.intelligence.analyze_symbol(symbol, market)
                    await self._record_prediction(symbol, market, signals)
                    await self.intelligence.process_signals(signals)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Analysis cycle failed for %s %s", market, symbol)

        while self._running:
            for market, enabled in (("SPOT", SPOT_ENABLED), ("FUTURES", USDM_FUTURES_ENABLED)):
                if not enabled:
                    continue
                tickers = self.cache.get_market_tickers(market)
                tickers.sort(
                    key=lambda item: float(item.get("volume_24h") or 0.0),
                    reverse=True,
                )
                if not tickers:
                    continue
                cursor = self._analysis_cursors[market] % len(tickers)
                batch = [
                    tickers[(cursor + offset) % len(tickers)]["symbol"]
                    for offset in range(min(self._analysis_batch_size, len(tickers)))
                ]
                self._analysis_cursors[market] = (cursor + len(batch)) % len(tickers)
                await asyncio.gather(*(analyze_one(market, symbol) for symbol in batch))
                self.disaster_recovery.watchdog.heartbeat()
            await asyncio.sleep(60)

    async def _record_prediction(self, symbol: str, market: str, signals: list[dict[str, Any]]) -> None:
        """Persist one leakage-safe prediction per newly closed 15m candle."""
        # Exchange candle timestamps are wall-clock epoch milliseconds.
        from datetime import datetime, timezone
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        ohlc_data: dict[str, dict[str, np.ndarray]] = {}
        for timeframe in ("15m", "1h", "4h", "1d"):
            closed = [
                candle for candle in self.candle_manager.get_series(
                    market, symbol, timeframe, limit=200
                )
                if candle["close_time"] <= now_ms
            ]
            if len(closed) >= 50:
                ohlc_data[timeframe] = {
                    "open": np.asarray([c["open"] for c in closed], dtype=np.float32),
                    "high": np.asarray([c["high"] for c in closed], dtype=np.float32),
                    "low": np.asarray([c["low"] for c in closed], dtype=np.float32),
                    "close": np.asarray([c["close"] for c in closed], dtype=np.float32),
                    "volume": np.asarray([c["volume"] for c in closed], dtype=np.float32),
                }

        primary = ohlc_data.get("15m")
        if primary is None or len(primary["close"]) < 50:
            return
        candle_open_time = int(self.candle_manager.get_series(
            market, symbol, "15m", limit=1
        )[-1]["open_time"])
        key = f"{market}:{symbol}"
        if self._last_prediction_candle.get(key) == candle_open_time:
            return

        features = self.feature_engine.build_features(symbol, market, ohlc_data)
        if features.size == 0 or not np.isfinite(features).all():
            return

        prediction = self.predictor.predict(features)
        linked_signal = max(
            signals,
            key=lambda item: float(item.get("raw_score", 0.0)),
            default=None,
        )
        if not self.predictor.is_trained:
            # Bootstrap labels from actual strategy signals until the first ML
            # model exists; do not manufacture predictions when no strategy fires.
            if linked_signal is None:
                return
            predicted_class = (
                "UP" if linked_signal["direction"] in ("LONG", "BUY") else "DOWN"
            )
            confidence = max(0.5, min(0.95, float(linked_signal.get("raw_score", 50.0)) / 100.0))
            residual = (1.0 - confidence) / 2.0
            probabilities = (
                (confidence, residual, residual) if predicted_class == "UP"
                else (residual, residual, confidence)
            )
            prob_up, prob_flat, prob_down = probabilities
        else:
            predicted_class = prediction["predicted_class"]
            confidence = float(prediction["confidence"])
            prob_up = float(prediction["prob_up"])
            prob_down = float(prediction["prob_down"])
            prob_flat = float(prediction["prob_flat"])

        prediction_id = f"PRED-{uuid.uuid4().hex}"
        self.repo.save_prediction({
            "prediction_id": prediction_id,
            "signal_id": linked_signal.get("signal_id") if linked_signal else None,
            "symbol": symbol,
            "market": market,
            "timeframe": "15m",
            "model_version": str(prediction.get("model_version", self.predictor.version)),
            "strategy_version": "hybrid-v1",
            "regime": linked_signal.get("regime", "UNKNOWN") if linked_signal else "UNKNOWN",
            "horizon_minutes": PREDICTION_HORIZON_MINUTES,
            "prob_up": prob_up,
            "prob_down": prob_down,
            "prob_flat": prob_flat,
            "predicted_class": predicted_class,
            "confidence": confidence,
            "feature_values": json.dumps(features.tolist()),
        })
        self._last_prediction_candle[key] = candle_open_time
        await self.event_bus.publish(make_event(
            EventType.PREDICTION,
            "learning",
            symbol=symbol,
            market=market,
            prediction_id=prediction_id,
            predicted_class=predicted_class,
            confidence=confidence,
        ))

    async def _learning_loop(self) -> None:
        """Run the outcome-labeling and hybrid retraining cycle once per hour."""
        while self._running:
            try:
                def run_cycle():
                    return asyncio.run(self.learning_orchestrator.run_learning_cycle())

                report = await asyncio.to_thread(run_cycle)
                learning_event = (
                    EventType.MODEL_TRAINED
                    if report.get("retrain", {}).get("status") == "trained"
                    else EventType.LEARNING_UPDATE
                )
                await self.event_bus.publish(make_event(
                    learning_event,
                    "learning",
                    **report,
                ))
                if report.get("promoted"):
                    await self.event_bus.publish(make_event(
                        EventType.MODEL_PROMOTED,
                        "learning",
                        version=report["promoted"],
                    ))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled learning cycle failed")
            await asyncio.sleep(3600)

    async def _persist_state(self) -> None:
        try:
            # Save open positions and a complete account snapshot. Closed trades
            # are already stored in trade_history, so omit them from this snapshot.
            for pos in self.simulator.spot_positions.values():
                self.repo.save_position(pos)
            for pos in self.simulator.futures_positions.values():
                self.repo.save_position(pos)
            snapshot = self.simulator.get_state_snapshot()
            snapshot["closed_trades"] = []
            self.repo.save_simulator_state(snapshot)
        except Exception as exc:
            logger.error("State persistence failed: %s", exc)

    async def stop(self) -> None:
        logger.info("Shutting down...")
        self._running = False
        await self.scanner.stop()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.disaster_recovery.ws_reconnection.stop()
        await self.ws_manager.stop()
        await self.spot_client.close()
        await self.futures_client.close()
        await self.event_bus.stop()
        if self._event_bus_task:
            await asyncio.gather(self._event_bus_task, return_exceptions=True)
            self._event_bus_task = None
        await self.disaster_recovery.stop()
        if self.telegram:
            await self.telegram.close()
        logger.info("Shutdown complete")

    async def handle_signal(self, sig: int, frame) -> None:
        logger.info("Received signal %s", sig)
        await self.stop()