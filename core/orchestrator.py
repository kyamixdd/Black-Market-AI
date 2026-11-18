"""Main orchestrator: coordinates all services and the intelligence bus."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import (
    PAPER_TRADING_ENABLED,
    SPOT_ENABLED,
    TELEGRAM_ENABLED,
    USDM_FUTURES_ENABLED,
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
        self.ws_manager: WebSocketManager = WebSocketManager(self.rate_limiter)
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
        # Learning accountability
        self.outcome_labeler = OutcomeLabeler(self.repo, self.simulator)
        self.performance_analyzer = PerformanceAnalyzer(self.repo)
        self.health_monitor: HealthMonitor = HealthMonitor()
        self._running: bool = False
        self._tasks: list[asyncio.Task] = []
        self._analysis_cursors: dict[str, int] = {"SPOT": 0, "FUTURES": 0}
        self._analysis_batch_size = 10
        self._analysis_timeframes = ("1m", "15m", "1h")
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
        # Risk alerts
        self.event_bus.subscribe(EventType.RISK_ALERT, self._on_risk_alert)
        # System health
        self.event_bus.subscribe(EventType.SYSTEM_HEALTH, self._on_system_health)
        # Model events
        self.event_bus.subscribe(EventType.MODEL_TRAINED, self._on_model_trained)
        self.event_bus.subscribe(EventType.MODEL_PROMOTED, self._on_model_promoted)
        self.event_bus.subscribe(EventType.MODEL_ROLLED_BACK, self._on_model_rolled_back)

    async def _on_signal_proposed(self, event) -> None:
        await self.decision_engine.evaluate_signal(event.payload)

    async def _on_signal_validated(self, event) -> None:
        if not PAPER_TRADING_ENABLED:
            return
        # Add strategy weight
        strategy = event.payload.get("strategy")
        regime = event.payload.get("regime")
        weight = self.strategy_selector.get_weight(strategy, regime)
        event.payload["_weight"] = weight
        await self.simulator.execute_signal(event.payload)

        # Send Telegram notification for strong setups (high confidence)
        if self.telegram and event.payload.get("confidence", 0) >= 0.75:
            await self.telegram.send_strong_setup(event.payload)

    async def _on_signal_rejected(self, event) -> None:
        if self.telegram:
            await self.telegram.send_signal_update(event.payload, "rejected")

    async def _on_signal_expired(self, event) -> None:
        if self.telegram:
            await self.telegram.send_signal_update(event.payload, "expired")

    async def _on_market_data(self, event) -> None:
        payload = event.payload
        market = payload.get("market", "SPOT")
        symbol = payload.get("symbol")
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
            if self.telegram:
                await self.telegram.send_position_closed(trade)

    async def _on_position_opened(self, event) -> None:
        position = event.payload.get("position")
        if position:
            self.repo.save_position(position)
            if self.telegram:
                await self.telegram.send_position_opened(position)

    async def _on_order_placed(self, event) -> None:
        self._persist_paper_order(event.payload.get("order"))

    async def _on_order_filled(self, event) -> None:
        self._persist_paper_order(event.payload.get("order"))

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
                await self.telegram.send_daily_risk_warning(
                    self.simulator.get_daily_pnl(),
                    self.simulator.spot_balance + self.simulator.futures_balance
                )
            elif alert_type == "MARGIN_RISK":
                await self.telegram.send_early_warning(
                    f"Margin risk: {payload.get('message', '')}",
                    payload.get("symbol", ""), payload.get("market", "")
                )
            elif alert_type == "LIQUIDATION":
                await self.telegram.send_early_warning(
                    f"LIQUIDATION: {payload.get('message', '')}",
                    payload.get("symbol", ""), payload.get("market", "")
                )

    async def _on_system_health(self, event) -> None:
        if self.telegram:
            payload = event.payload
            await self.telegram.send_connection_status(
                payload.get("component", "SYSTEM"),
                payload.get("status", "unknown"),
                payload.get("message", "")
            )

    async def _on_model_trained(self, event) -> None:
        if self.telegram:
            await self.telegram.send_learning_report(event.payload)

    async def _on_model_promoted(self, event) -> None:
        if self.telegram:
            await self.telegram.send_message(f"🚀 <b>MODEL PROMOTED</b>\n\nVersion: {event.payload.get('version', 'unknown')}")

    async def _on_model_rolled_back(self, event) -> None:
        if self.telegram:
            await self.telegram.send_message(f"↩️ <b>MODEL ROLLED BACK</b>\n\nVersion: {event.payload.get('version', 'unknown')}")

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
        await self.scanner.start()
        self._tasks.append(asyncio.create_task(self._analysis_loop(), name="blackmarket-analysis"))
        logger.info("BlackMarket AI running")
        # Main loop - keep running until stopped
        while self._running:
            await asyncio.sleep(60)
            self.disaster_recovery.watchdog.heartbeat()
            # Periodic persistence
            await self._persist_state()

    async def _analysis_loop(self) -> None:
        """Rotate through the complete eligible universe and run real strategy analysis.

        Ticker discovery covers every eligible symbol. Candle-heavy analysis is
        deliberately batched to respect public exchange rate limits on a desktop PC.
        """
        semaphore = asyncio.Semaphore(4)

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
                            limit=500,
                        )
                        candles = self.candle_manager.get_series(
                            market, symbol, timeframe, limit=500
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
                    for signal in signals:
                        await self.event_bus.publish(make_event(
                            EventType.SIGNAL_PROPOSED,
                            "intelligence",
                            **signal,
                        ))
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
            await asyncio.sleep(60)

    async def _persist_state(self) -> None:
        try:
            # Save open positions
            for pos in self.simulator.spot_positions.values():
                self.repo.save_position(pos)
            for pos in self.simulator.futures_positions.values():
                self.repo.save_position(pos)
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
        await self.disaster_recovery.stop()
        logger.info("Shutdown complete")

    async def handle_signal(self, sig: int, frame) -> None:
        logger.info("Received signal %s", sig)
        await self.stop()