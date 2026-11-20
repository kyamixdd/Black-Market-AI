"""Main orchestrator: coordinates all services and the intelligence bus."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import (
    AUTO_MODEL_TRAINING,
    PAPER_TRADING_ENABLED,
    SPOT_ENABLED,
    TELEGRAM_ENABLED,
    USDM_FUTURES_ENABLED,
)
from core.event_bus import EventBus
from core.disaster_recovery import create_disaster_recovery_orchestrator
from core.event_models import EventType
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
from learning.live_service import LiveLearningService
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
        self.integrity: DataIntegrityGuardian = DataIntegrityGuardian(self.candle_manager)
        self.intelligence: IntelligenceCore = IntelligenceCore(
            self.event_bus, self.candle_manager, self.integrity
        )
        self.decision_engine: DecisionEngine = self.intelligence.decision_engine
        self.strategy_selector: StrategySelector = self.intelligence.strategy_selector
        self.feature_engine: FeatureEngine = self.intelligence.feature_engine
        self.predictor: Predictor = self.intelligence.predictor
        self.simulator: Simulator = Simulator(self.event_bus, self.cache)
        self.scanner: Scanner = Scanner(
            self.event_bus, self.registry, self.cache,
            self.spot_client, self.futures_client,
            self.candle_manager, self.intelligence,
        )
        self.telegram: TelegramClient | None = TelegramClient() if TELEGRAM_ENABLED else None
        # Keep one canonical predictor for the API, live inference, and learning loop.
        self.learning_service = LiveLearningService(self)
        # Learning accountability
        self.outcome_labeler = OutcomeLabeler(self.repo, self.simulator)
        self.performance_analyzer = PerformanceAnalyzer(self.repo)
        self.health_monitor: HealthMonitor = HealthMonitor()
        self._runtime_settings = {}
        self._running: bool = False
        self._tasks: list[asyncio.Task] = []
        self._discovery: MarketDiscovery = MarketDiscovery(self.registry, self.rate_limiter,
                                                        SPOT_ENABLED, USDM_FUTURES_ENABLED)
        # State tracking for dashboard
        self._scanning: bool = False
        self._ws_connected: bool = False
        self._tracked_symbols: list[str] = []
        self._recent_snapshots: list[dict] = []
        self._current_regime: str = "UNKNOWN"
        self.apply_runtime_settings(self._load_runtime_settings(), persist=False)

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

    @staticmethod
    def _load_runtime_settings() -> dict:
        from core.runtime_settings_store import load_runtime_settings
        from src_tauri.backend.api.routes.schemas import SettingsRequest
        saved = load_runtime_settings()
        if not saved:
            return {}
        return SettingsRequest.model_validate(saved).model_dump(exclude_none=True)

    def apply_runtime_settings(self, settings: dict, persist: bool = True) -> None:
        """Apply validated settings to live components; never reset active paper equity."""
        from core.runtime_settings_store import save_runtime_settings

        if not isinstance(settings, dict):
            raise ValueError("Runtime settings must be an object.")
        simulator = self.simulator
        risk = simulator.risk_manager
        has_activity = bool(
            simulator.spot_positions or simulator.futures_positions
            or simulator.open_orders or simulator.closed_trades
        )
        balance_changed = (
            settings.get("spot_initial_balance", simulator.initial_spot_balance) != simulator.initial_spot_balance
            or settings.get("futures_initial_balance", simulator.initial_futures_balance) != simulator.initial_futures_balance
        )
        if balance_changed and has_activity:
            raise ValueError("Paper starting balances cannot be changed after trading activity exists.")

        from config import (
            SPOT_ENABLED, USDM_FUTURES_ENABLED, SCAN_ALL_ELIGIBLE_SYMBOLS,
            TIMEFRAMES, TELEGRAM_ENABLED,
        )
        from src_tauri.backend.api.routes.schemas import SettingsRequest

        # Validate the complete effective configuration, not just fields present
        # in this PATCH-like request. This prevents partial updates from making
        # combinations invalid (for example risk/trade above total open risk).
        effective = {
            "spot_enabled": self._discovery.spot_enabled,
            "futures_enabled": self._discovery.futures_enabled,
            "scan_all_eligible_symbols": self.scanner.analysis_symbol_limit > 10,
            "timeframes": list(self.scanner.analysis_timeframes),
            "spot_initial_balance": simulator.initial_spot_balance,
            "futures_initial_balance": simulator.initial_futures_balance,
            "risk_per_trade_pct": risk.max_risk_pct,
            "risk_max_daily_loss_pct": risk.max_daily_loss_pct,
            "risk_max_total_open_pct": risk.max_open_risk_pct,
            "risk_max_leverage": risk.max_leverage,
            "max_spot_positions": risk.max_spot_positions,
            "max_futures_positions": risk.max_futures_positions,
            "telegram_enabled": self.telegram is not None,
        }
        next_settings = SettingsRequest.model_validate({
            **effective, **self._runtime_settings, **settings
        }).model_dump(exclude_none=True)

        telegram_enabled = bool(next_settings.get("telegram_enabled", TELEGRAM_ENABLED))
        if telegram_enabled:
            from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
                raise ValueError("Telegram cannot be enabled until its bot token and chat ID are configured in the private environment.")

        # Persist the complete next state before mutating live components. A failed
        # disk write therefore leaves the running engine on its previous settings.
        if persist:
            save_runtime_settings(next_settings)

        # Apply numeric risk controls only after request schema validation.
        risk.max_risk_pct = float(next_settings.get("risk_per_trade_pct", risk.max_risk_pct))
        risk.max_daily_loss_pct = float(next_settings.get("risk_max_daily_loss_pct", risk.max_daily_loss_pct))
        risk.max_open_risk_pct = float(next_settings.get("risk_max_total_open_pct", risk.max_open_risk_pct))
        risk.max_leverage = float(next_settings.get("risk_max_leverage", risk.max_leverage))
        risk.max_spot_positions = int(next_settings.get("max_spot_positions", risk.max_spot_positions))
        risk.max_futures_positions = int(next_settings.get("max_futures_positions", risk.max_futures_positions))

        if balance_changed:
            spot = float(next_settings.get("spot_initial_balance", simulator.initial_spot_balance))
            futures = float(next_settings.get("futures_initial_balance", simulator.initial_futures_balance))
            simulator.initial_spot_balance = simulator.spot_balance = spot
            simulator.initial_futures_balance = simulator.futures_balance = futures

        scanner = self.scanner
        scanner.enabled_markets = {
            market for market, enabled in (
                ("SPOT", next_settings.get("spot_enabled", True)),
                ("FUTURES", next_settings.get("futures_enabled", True)),
            ) if enabled
        }
        scanner.analysis_timeframes = tuple(next_settings.get("timeframes", ("15m", "1h")))
        scanner.analysis_symbol_limit = 50 if next_settings.get("scan_all_eligible_symbols", False) else 10
        self._discovery.spot_enabled = bool(next_settings.get("spot_enabled", True))
        self._discovery.futures_enabled = bool(next_settings.get("futures_enabled", True))

        if telegram_enabled and self.telegram is None:
            self.telegram = TelegramClient()
        elif not telegram_enabled:
            self.telegram = None

        self._runtime_settings = next_settings



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
        self.event_bus.subscribe(EventType.MARKET_SNAPSHOT, self._on_market_snapshot)
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
        if price and symbol:
            await self.simulator.update_prices(market, symbol, price)

    async def _on_market_snapshot(self, event) -> None:
        """Mark open positions and check pending limits from the scanner's latest cache."""
        market = event.market or event.payload.get("market", "SPOT")
        positions = self.simulator._get_positions(market)
        symbols = {
            position.get("symbol") for position in positions.values()
            if position.get("status") == "OPEN"
        }
        for symbol in symbols:
            snapshot = self.cache.get_snapshot(market, symbol)
            if not snapshot:
                continue
            price = snapshot.get("price")
            if not price or price <= 0:
                continue
            await self.simulator.update_prices(
                market, symbol, price,
                mark_price=snapshot.get("mark_price"),
                funding_rate=snapshot.get("funding_rate"),
            )

        pending_symbols = {
            order.get("symbol") for order in self.simulator.open_orders.values()
            if order.get("market") == market and order.get("status") == "OPEN"
        }
        for symbol in pending_symbols:
            price = self.cache.get_price(market, symbol)
            if price and price > 0:
                await self.simulator.check_limit_orders(market, symbol, price)

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
        if AUTO_MODEL_TRAINING:
            self._tasks.append(asyncio.create_task(
                self.learning_service.run(), name="blackmarket-live-learning"
            ))
        else:
            self.learning_service.state = "disabled"
            self.learning_service.last_cycle_status = "AUTO_MODEL_TRAINING is disabled"
        logger.info("BlackMarket AI running")
        # Main loop - keep running until stopped
        while self._running:
            await asyncio.sleep(60)
            self.disaster_recovery.watchdog.heartbeat()
            # Periodic persistence
            await self._persist_state()

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
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
        await self.scanner.stop()
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
