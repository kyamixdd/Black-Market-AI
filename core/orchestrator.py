"""Main orchestrator: coordinates all services and the intelligence bus."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
import numpy as np
from datetime import datetime, timezone
from typing import Any

from config import (
    AUTO_MODEL_TRAINING,
    PAPER_TRADING_ENABLED,
    AUTO_PAPER_TRADING_ENABLED,
    SPOT_ENABLED,
    SIGNAL_STALE_SECONDS,
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
        self._confidence_threshold_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.simulator.persist_order_callback = self._persist_paper_order
        self.simulator.persist_position_callback = self.repo.save_position
        self.simulator.persist_trade_callback = self.repo.save_trade_history
        self.simulator.persist_partial_trade_callback = self.repo.save_partial_trade
        self.scanner: Scanner = Scanner(
            self.event_bus, self.registry, self.cache,
            self.spot_client, self.futures_client,
            self.candle_manager, self.intelligence,
            websocket_manager=self.ws_manager,
        )
        self.telegram: TelegramClient | None = TelegramClient() if TELEGRAM_ENABLED else None
        # Keep one canonical predictor for the API, live inference, and learning loop.
        self.learning_service = LiveLearningService(self)
        # Learning accountability
        self.outcome_labeler = OutcomeLabeler(self.repo, self.simulator)
        self.performance_analyzer = PerformanceAnalyzer(self.repo)
        self.health_monitor: HealthMonitor = HealthMonitor()
        self._runtime_settings = {}
        self._autonomous_enabled = AUTO_PAPER_TRADING_ENABLED
        self.last_autonomous_decision: dict[str, Any] | None = None
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
        from core.daily_equity_state import load_daily_equity_state, save_daily_equity_state
        self.simulator.persist_daily_equity_callback = save_daily_equity_state
        daily_state = load_daily_equity_state()
        today = datetime.now(timezone.utc).date()
        if daily_state and daily_state["date"] == today:
            self.simulator.daily_pnl_date = today
            self.simulator.daily_start_equity = daily_state["equity"]
            self.simulator.daily_equity_state_loaded = True

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
            AUTO_PAPER_TRADING_ENABLED,
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
            "risk_max_position_size_pct": risk.max_position_size_pct,
            "risk_max_asset_exposure_pct": risk.max_asset_exposure_pct,
            "max_spot_positions": risk.max_spot_positions,
            "max_futures_positions": risk.max_futures_positions,
            "telegram_enabled": self.telegram is not None,
            "autonomous_enabled": self._autonomous_enabled if self._runtime_settings else AUTO_PAPER_TRADING_ENABLED,
            "telegram_notify_decisions": True,
            "telegram_notify_executions": True,
            "telegram_notify_risk": True,
            "telegram_notify_learning": True,
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
        risk.max_position_size_pct = float(next_settings.get("risk_max_position_size_pct", risk.max_position_size_pct))
        risk.max_asset_exposure_pct = float(next_settings.get("risk_max_asset_exposure_pct", risk.max_asset_exposure_pct))
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
        self._autonomous_enabled = bool(next_settings.get("autonomous_enabled", AUTO_PAPER_TRADING_ENABLED))



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

    def refresh_health_status(self) -> dict[str, Any]:
        """Publish current runtime readiness for diagnostics and dashboards."""
        scanner = self.scanner.status_snapshot()
        enabled_markets = self.scanner.enabled_markets
        market_statuses = scanner.get("markets", {})
        scan_failures = {
            market: market_statuses.get(market, {}).get("refresh_failures", 0)
            for market in enabled_markets
        }
        scanner_healthy = bool(enabled_markets) and scanner.get("running", False) and all(
            market_statuses.get(market, {}).get("state") in {"SCANNING", "COMPLETE"}
            and not market_statuses.get(market, {}).get("last_error")
            and not scan_failures[market]
            for market in enabled_markets
        )
        scanner_details = None
        if not scanner_healthy:
            scanner_details = "; ".join(
                f"{market}: {market_statuses.get(market, {}).get('state', 'UNAVAILABLE')}"
                f" ({scan_failures.get(market, 0)} refresh failures)"
                for market in sorted(enabled_markets)
            ) or "No markets are enabled."

        websocket = self.ws_manager.status_snapshot()
        websocket_state = websocket.get("state", "UNKNOWN")
        websocket_healthy = not enabled_markets or websocket_state == "LIVE"
        websocket_details = (
            None if websocket_healthy
            else f"Exchange WebSocket state is {websocket_state}."
        )

        predictor = self.intelligence.predictor
        model_available = bool(predictor.is_trained)
        learning_state = getattr(self.learning_service, "state", "unknown")
        training_result = getattr(self.learning_service, "last_training_result", None) or {}
        model_details = None
        if not model_available:
            reason = training_result.get("reason") if isinstance(training_result, dict) else None
            model_details = "No validated active model"
            if reason:
                model_details += f": {reason}"
            else:
                model_details += f" (learning state: {learning_state})"

        self.health_monitor.check_component(
            "database",
            self.db is not None,
            None if self.db is not None else "Database is not initialized.",
        )
        self.health_monitor.check_component(
            "market_scanner",
            scanner_healthy,
            scanner_details,
        )
        self.health_monitor.check_component(
            "exchange_websocket",
            websocket_healthy,
            websocket_details,
        )
        self.health_monitor.check_component(
            "learning_model",
            model_available,
            model_details,
        )
        self.health_monitor.check_component(
            "paper_trading",
            self.simulator is not None,
            None if PAPER_TRADING_ENABLED else "Paper trading is disabled by configuration.",
        )
        self.health_monitor.update_metrics({
            "scanner": {
                "running": scanner.get("running", False),
                "configured_timeframes": scanner.get("configured_timeframes", []),
                "markets": market_statuses,
            },
            "eligible_symbols": {
                market: self.registry.count(market)
                for market in ("SPOT", "FUTURES")
            },
            "exchange_websocket": websocket,
            "learning": {
                "state": learning_state,
                "active_model_available": model_available,
                "last_cycle_status": getattr(self.learning_service, "last_cycle_status", "unknown"),
            },
            "paper_trading": {
                "enabled": PAPER_TRADING_ENABLED,
                "autonomous_entries_enabled": self._autonomous_enabled,
            },
        })
        return self.health_monitor.get_status()

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
        self.event_bus.subscribe(EventType.TRADE_CANCELLED, self._on_order_cancelled)
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

    @staticmethod
    def _predictor_matches_active_registry(model_version: str, registry: list) -> bool:
        active = [item for item in registry if bool(getattr(item, "is_active", False))]
        if model_version.startswith("river_"):
            return any(
                getattr(item, "model_type", "") == "river"
                and getattr(item, "version", "") == model_version
                for item in active
            )
        return all(
            any(
                getattr(item, "model_type", "") == model_type
                and getattr(item, "version", "") == f"{model_type}_{model_version}"
                for item in active
            )
            for model_type in ("random_forest", "xgboost")
        )

    def _live_paper_confidence_gate(self, signal: dict[str, Any]) -> tuple[bool, str]:
        """Require a matching active model and historically calibrated threshold."""
        from learning.confidence_gate import (
            calibrate_model_confidence_threshold,
            evaluate_live_confidence,
        )

        predictor = self.intelligence.predictor
        model_version = str(getattr(predictor, "version", "") or "")
        if not getattr(predictor, "is_trained", False) or not model_version or model_version == "0001":
            signal["_model_evidence"] = {"available": False, "model_version": model_version or None}
            return False, "active_trained_model_unavailable"

        try:
            registry = self.repo.get_model_registry()
            if not self._predictor_matches_active_registry(model_version, registry):
                signal["_model_evidence"] = {"available": False, "model_version": model_version, "reason": "predictor_does_not_match_active_model_registry"}
                return False, "predictor_does_not_match_active_model_registry"

            cached = self._confidence_threshold_cache.get(model_version)
            if cached and time.monotonic() - cached[0] < 300:
                calibration = cached[1]
            else:
                historical = self.repo.get_predictions_history(10000)
                calibration = calibrate_model_confidence_threshold(
                    historical, model_version, min_samples=20
                )
                self._confidence_threshold_cache[model_version] = (time.monotonic(), calibration)
            if calibration.get("status") != "selected_from_historical_calibration":
                return False, str(calibration.get("status", "model_not_calibrated"))

            market, symbol = signal.get("market"), signal.get("symbol")
            if market not in {"SPOT", "FUTURES"} or not symbol:
                return False, "signal_market_or_symbol_unavailable"
            snapshot = self.cache.get_snapshot(market, symbol)
            timestamp = snapshot.get("timestamp") if snapshot else None
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if timestamp is None:
                return False, "market_snapshot_timestamp_unavailable"
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            data_age = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if data_age < -5 or data_age > SIGNAL_STALE_SECONDS:
                return False, f"market_data_stale:{max(0, int(data_age))}s"
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            ohlc_data = {}
            for timeframe in ("15m", "1h", "4h", "1d"):
                candles = [
                    candle for candle in self.candle_manager.get_series(
                        market, symbol, timeframe, limit=200
                    )
                    if int(candle.get("close_time", 0)) < now_ms
                ]
                if len(candles) < 50:
                    return False, f"insufficient_closed_{timeframe}_candles"
                ohlc_data[timeframe] = {
                    name: np.asarray([item[name] for item in candles], dtype=np.float32)
                    for name in ("open", "high", "low", "close", "volume")
                }
            features = self.feature_engine.build_features(symbol, market, ohlc_data)
            if features.shape != (36,) or not np.isfinite(features).all():
                return False, "live_model_features_unavailable"
            prediction = predictor.predict(features)
            predicted_class = str(prediction.get("predicted_class", "")).upper()
            signal_id = str(signal.get("signal_id", ""))
            prediction_id = f"signal:{signal_id}"[:64] if signal_id else f"signal:{uuid.uuid4().hex}"
            if predicted_class in {"UP", "DOWN", "FLAT"}:
                probabilities = [prediction.get("prob_up"), prediction.get("prob_down"), prediction.get("prob_flat")]
                if all(value is not None and np.isfinite(float(value)) for value in probabilities):
                    self.repo.save_prediction({
                        "prediction_id": prediction_id,
                        "signal_id": signal_id or None,
                        "symbol": symbol,
                        "market": market,
                        "timeframe": str(signal.get("timeframe") or "1h"),
                        "model_version": model_version[:32],
                        "strategy_version": str(signal.get("strategy") or "live_signal")[:32],
                        "regime": str(signal.get("regime") or "UNKNOWN")[:32],
                        "horizon_minutes": 60,
                        "prob_up": float(probabilities[0]),
                        "prob_down": float(probabilities[1]),
                        "prob_flat": float(probabilities[2]),
                        "predicted_class": predicted_class,
                        "confidence": float(prediction.get("confidence", 0.0)),
                        "feature_values": json.dumps(features.astype(float).tolist()),
                        "created_at": datetime.now(timezone.utc),
                    })
            signal["_model_evidence"] = {
                "available": True,
                "model_version": model_version,
                "prediction_id": prediction_id,
                "predicted_class": predicted_class,
                "confidence": prediction.get("confidence"),
                "prob_up": prediction.get("prob_up"),
                "prob_down": prediction.get("prob_down"),
                "prob_flat": prediction.get("prob_flat"),
                "market_data_age_seconds": max(0.0, data_age),
            }
            if predicted_class not in {"UP", "DOWN"}:
                return False, "model_prediction_not_directional"
            strategy_direction = str(signal.get("direction", "")).upper()
            expected_class = "UP" if strategy_direction in {"LONG", "BUY"} else "DOWN" if strategy_direction in {"SHORT", "SELL"} else None
            if expected_class is None or predicted_class != expected_class:
                return False, "model_strategy_disagreement"
            allowed, reason = evaluate_live_confidence(
                prediction.get("confidence"),
                calibration.get("threshold"),
                model_version,
                calibration.get("model_version"),
            )
            if not allowed:
                return False, reason
            return True, reason
        except Exception:
            logger.exception("Live paper confidence gate failed closed for %s", signal.get("signal_id"))
            return False, "confidence_gate_error"

    async def _on_signal_validated(self, event) -> None:
        signal = self._signal_payload(event)
        if not PAPER_TRADING_ENABLED:
            self._record_autonomous_decision(signal, "BLOCKED", "paper_trading_disabled")
            return
        if not getattr(self, "_autonomous_enabled", AUTO_PAPER_TRADING_ENABLED):
            self._record_autonomous_decision(signal, "PAUSED", "autonomous_entries_paused")
            return
        allowed, reason = self._live_paper_confidence_gate(signal)
        if not allowed:
            self._record_autonomous_decision(signal, "BLOCKED", reason)
            logger.info(
                "Paper signal %s skipped by historical confidence gate: %s",
                signal.get("signal_id"), reason,
            )
            if self.telegram and self._telegram_preference("decisions"):
                await self.telegram.send_autonomous_decision(self.last_autonomous_decision)
            return
        # Add strategy weight
        strategy = signal.get("strategy")
        regime = signal.get("regime")
        weight = self.strategy_selector.get_weight(strategy, regime)
        signal["_weight"] = weight
        risk_ok, risk_reason = self.simulator.validate_new_position(signal)
        if not risk_ok:
            self._record_autonomous_decision(signal, "RISK_REJECTED", risk_reason)
            if self.telegram and self._telegram_preference("risk"):
                await self.telegram.send_autonomous_decision(self.last_autonomous_decision)
            return
        position_id = await self.simulator.execute_signal(signal)
        if not position_id:
            self._record_autonomous_decision(signal, "EXECUTION_REJECTED", "paper_simulator_rejected_after_risk_recheck")
            if self.telegram and self._telegram_preference("executions"):
                await self.telegram.send_autonomous_decision(self.last_autonomous_decision)
            return
        self._record_autonomous_decision(signal, "EXECUTED", "paper_position_opened", position_id=position_id)
        if self.telegram and self._telegram_preference("executions"):
            await self.telegram.send_autonomous_decision(self.last_autonomous_decision)

    async def _on_signal_rejected(self, event) -> None:
        signal = self._signal_payload(event)
        self._record_autonomous_decision(signal, "SIGNAL_REJECTED", signal.get("reason", "strategy_signal_rejected"))
        if self.telegram and self._telegram_preference("decisions"):
            await self.telegram.send_signal_update(signal, "rejected")

    @staticmethod
    def _signal_payload(event) -> dict[str, Any]:
        """Restore signal identity fields stored on the event envelope."""
        signal = dict(event.payload)
        if getattr(event, "symbol", None) and not signal.get("symbol"):
            signal["symbol"] = event.symbol
        if getattr(event, "market", None) and not signal.get("market"):
            signal["market"] = event.market
        return signal

    def _record_autonomous_decision(self, signal: dict[str, Any], status: str, reason: str, *, position_id: str | None = None) -> dict[str, Any]:
        """Persist the evidence and outcome for one strategy signal decision."""
        direction = str(signal.get("direction", "")).upper()
        entry = signal.get("entry")
        stop = signal.get("stop_loss")
        targets = signal.get("take_profit") or []
        target = targets[0] if targets else None
        risk = abs(float(entry) - float(stop)) if entry is not None and stop is not None else None
        reward = abs(float(target) - float(entry)) if target is not None and entry is not None else None
        market = signal.get("market")
        balance = self.simulator.get_balance(str(market or "SPOT"))
        can_size = risk and market in {"SPOT", "FUTURES"} and all(
            signal.get(key) is not None for key in ("symbol", "direction", "entry", "stop_loss")
        )
        try:
            quantity, _ = self.simulator._calculate_order_quantity(signal, balance) if can_size else (None, None)
        except (KeyError, TypeError, ValueError, OverflowError):
            quantity = None
        decision = {
            "status": status,
            "reason": reason,
            "signal_id": signal.get("signal_id"),
            "symbol": signal.get("symbol"),
            "market": signal.get("market"),
            "strategy": signal.get("strategy"),
            "strategy_direction": direction or None,
            "entry": entry,
            "stop_loss": stop,
            "take_profit": target,
            "position_size": quantity,
            "risk_reward": reward / risk if risk and reward is not None else None,
            "strategy_score": signal.get("confidence"),
            "model": signal.get("_model_evidence"),
            "regime": signal.get("regime"),
            "decision_time": datetime.now(timezone.utc).isoformat(),
            "invalidation": ["stop_loss", "take_profit", "stale_market_data", "risk_limits"],
            "position_id": position_id,
        }
        self.last_autonomous_decision = decision
        try:
            self.repo.save_system_event({
                "event_id": f"AUTODEC-{signal.get('signal_id') or uuid.uuid4().hex}-{status}"[:64],
                "event_type": "AUTONOMOUS_DECISION",
                "source": "autonomous_engine",
                "symbol": decision["symbol"],
                "market": decision["market"],
                "payload": decision,
            })
        except Exception:
            logger.exception("Could not persist autonomous decision for signal %s", signal.get("signal_id"))
        return decision

    def _telegram_preference(self, category: str) -> bool:
        return bool(self._runtime_settings.get(f"telegram_notify_{category}", True))

    def get_autonomous_status(self) -> dict[str, Any]:
        predictor = self.intelligence.predictor
        try:
            spot = self.cache.get_data_status("SPOT")
            futures = self.cache.get_data_status("FUTURES")
            models = self.repo.get_model_registry()
            active_model = bool(
                getattr(predictor, "is_trained", False)
                and self._predictor_matches_active_registry(str(getattr(predictor, "version", "") or ""), models)
            )
            readiness = []
            if not PAPER_TRADING_ENABLED:
                readiness.append("paper_trading_disabled")
            enabled_markets = getattr(getattr(self, "scanner", None), "enabled_markets", set())
            live_market_ready = any(
                market in enabled_markets and status.get("state") in {"LIVE", "DELAYED"}
                for market, status in (("SPOT", spot), ("FUTURES", futures))
            )
            if not live_market_ready:
                readiness.append("fresh_market_data_unavailable")
            if not getattr(predictor, "is_trained", False) or not active_model:
                readiness.append("no_active_validated_model")
            elif getattr(predictor, "version", None):
                from learning.confidence_gate import calibrate_model_confidence_threshold
                cached = self._confidence_threshold_cache.get(str(predictor.version))
                calibration = cached[1] if cached and time.monotonic() - cached[0] < 300 else calibrate_model_confidence_threshold(
                    self.repo.get_predictions_history(10000), str(predictor.version), min_samples=20
                )
                if calibration.get("status") != "selected_from_historical_calibration":
                    readiness.append("model_confidence_not_calibrated")
                self._confidence_threshold_cache[str(predictor.version)] = (time.monotonic(), calibration)
            if not self._running:
                readiness.append("backend_engine_stopped")
            risk_manager = self.simulator.risk_manager
            daily_pnl = self.simulator.get_daily_pnl()
            daily_equity = self.simulator.get_daily_equity_baseline()
            daily_loss_pct = max(0.0, -daily_pnl) / daily_equity * 100.0 if daily_equity > 0 else 100.0
            daily_risk_ready = risk_manager.check_daily_loss(daily_pnl, daily_equity)
            if not daily_risk_ready:
                readiness.append("daily_loss_limit_reached")
            latest = self.last_autonomous_decision
            if latest is None:
                persisted = self.get_autonomous_decisions(1)
                latest = persisted[0] if persisted else None
            return {
                "mode": "PAPER_ONLY",
                "enabled": self._autonomous_enabled,
                "running": self._running,
                "entry_ready": not readiness,
                "readiness_reasons": readiness,
                "model_available": bool(getattr(predictor, "is_trained", False) and active_model),
                "model_version": getattr(predictor, "version", None) if getattr(predictor, "is_trained", False) else None,
                "paper_trading_enabled": PAPER_TRADING_ENABLED,
                "markets": {"SPOT": spot, "FUTURES": futures},
                "open_positions": len(self.simulator.spot_positions) + len(self.simulator.futures_positions),
                "open_orders": len(self.simulator.open_orders),
                "strategies": [getattr(strategy, "name", type(strategy).__name__) for strategy in self.intelligence.get_strategies()],
                "risk": {
                    "paused": not daily_risk_ready,
                    "daily_loss_pct": daily_loss_pct,
                    "max_daily_loss_pct": getattr(risk_manager, "max_daily_loss_pct", None),
                },
                "last_decision": latest,
                "learning": {"state": self.learning_service.state, "last_cycle_status": self.learning_service.last_cycle_status},
                "telegram": self.telegram.status() if self.telegram else {"enabled": False, "configured": False, "connected": False},
            }
        except Exception:
            logger.exception("Autonomous status calculation failed")
            return {"mode": "PAPER_ONLY", "enabled": self._autonomous_enabled, "running": self._running, "entry_ready": False, "readiness_reasons": ["status_check_failed"]}

    async def _on_signal_expired(self, event) -> None:
        if self.telegram and self._telegram_preference("decisions"):
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
        trade = event.payload.get("trade")
        if trade:
            self.repo.save_trade_history(trade)
            if self.telegram and self._telegram_preference("executions"):
                await self.telegram.send_position_closed(trade)

    async def _on_position_opened(self, event) -> None:
        position = event.payload.get("position")
        if position:
            self.repo.save_position(position)
            if self.telegram and self._telegram_preference("executions"):
                await self.telegram.send_position_opened(position)

    async def _on_order_placed(self, event) -> None:
        self._persist_paper_order(event.payload.get("order"))

    async def _on_order_filled(self, event) -> None:
        order = event.payload.get("order")
        if not order or not order.get("_durably_persisted"):
            self._persist_paper_order(order)

    async def _on_order_cancelled(self, event) -> None:
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
        if self.telegram and self._telegram_preference("risk") and alert_type in ("DAILY_LOSS", "MARGIN_RISK", "LIQUIDATION"):
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
        if self.telegram and self._telegram_preference("risk"):
            payload = event.payload
            await self.telegram.send_connection_status(
                payload.get("component", "SYSTEM"),
                payload.get("status", "unknown"),
                payload.get("message", "")
            )

    async def _handle_telegram_command(self, text: str) -> str:
        """Handle controls only after TelegramClient has verified the chat ID."""
        command = text.split()[0].split("@", 1)[0].lower()
        if command == "/help":
            return "Commands: /status /pause /resume /positions /balance /performance /learning /help. All execution is PAPER ONLY."
        if command == "/pause":
            self.apply_runtime_settings({"autonomous_enabled": False})
            return "Autonomous entries paused. Open positions continue to be monitored and may exit at risk limits."
        if command == "/resume":
            status = self.get_autonomous_status()
            if not status.get("entry_ready"):
                return "Resume blocked: " + ", ".join(status.get("readiness_reasons", ["engine_not_ready"]))
            self.apply_runtime_settings({"autonomous_enabled": True})
            return "Autonomous paper entries resumed after readiness checks. Real trading is disabled."
        if command == "/status":
            status = self.get_autonomous_status()
            readiness = "ready" if status.get("entry_ready") else ", ".join(status.get("readiness_reasons", []))
            return f"Backend: {'running' if status.get('running') else 'stopped'}\nMode: PAPER ONLY\nEntries: {'enabled' if status.get('enabled') else 'paused'}\nReadiness: {readiness}"
        if command == "/positions":
            positions = [*self.simulator.spot_positions.values(), *self.simulator.futures_positions.values()]
            if not positions:
                return "No open paper positions."
            return "Open paper positions:\n" + "\n".join(
                f"{p.get('symbol')} {p.get('market')} {p.get('side')} · qty {float(p.get('amount', 0)):.8g} · unrealized {float(p.get('unrealized_pnl', 0)):.2f}"
                for p in positions[:30]
            )
        if command == "/balance":
            return (
                f"Spot paper balance: {self.simulator.spot_balance:.2f} USDT\n"
                f"Futures paper balance: {self.simulator.futures_balance:.2f} USDT\n"
                f"Total equity: {self.simulator.get_account_equity_breakdown()['total_equity']:.2f} USDT"
            )
        if command == "/performance":
            trades = self.repo.get_trade_history(limit=None)
            pnls = [float(item.pnl or 0.0) for item in trades]
            wins = sum(value > 0 for value in pnls)
            return (
                f"Closed paper trades: {len(trades)}\n"
                f"Realized PnL: {sum(pnls):.4f} USDT\n"
                f"Win rate: {(wins / len(trades) * 100):.2f}%" if trades else
                "No closed paper trades are available for performance reporting."
            )
        if command == "/learning":
            summary = self.learning_service._training_summary(self.learning_service.last_training_result or {})
            return (
                f"Learning state: {self.learning_service.state}\n"
                f"Last cycle: {self.learning_service.last_cycle_status}\n"
                f"Bootstrap samples: {self.learning_service.training_samples}\n"
                f"Online updates: {self.learning_service.river_updates}\n"
                f"Last validation: {(summary or {}).get('status', 'not available')}"
            )
        return "Unknown command. Send /help for available commands."

    def get_autonomous_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        decisions = []
        for event in self.repo.get_system_events(limit=min(max(limit * 4, 50), 1000)):
            if event.event_type != "AUTONOMOUS_DECISION":
                continue
            try:
                payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
            except (TypeError, json.JSONDecodeError):
                payload = {}
            decisions.append({
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "symbol": event.symbol,
                "market": event.market,
                **(payload if isinstance(payload, dict) else {}),
            })
            if len(decisions) >= limit:
                break
        return decisions

    async def _on_model_trained(self, event) -> None:
        if self.telegram and self._telegram_preference("learning"):
            await self.telegram.send_learning_report(event.payload)

    async def _on_model_promoted(self, event) -> None:
        if self.telegram and self._telegram_preference("learning"):
            await self.telegram.send_message(f"🚀 <b>MODEL PROMOTED</b>\n\nVersion: {event.payload.get('version', 'unknown')}")

    async def _on_model_rolled_back(self, event) -> None:
        if self.telegram and self._telegram_preference("learning"):
            await self.telegram.send_message(f"↩️ <b>MODEL ROLLED BACK</b>\n\nVersion: {event.payload.get('version', 'unknown')}")

    async def _persist_event(self, event) -> None:
        """Persist critical events to SQLite for state recovery after interruptions."""
        # Price and ticker events are streamed continuously; retaining every
        # tick here can bury actionable system events in the Activity feed.
        if event.event_type == EventType.MARKET_DATA:
            return
        try:
            # Event payloads can contain datetimes and other values supported by
            # Pydantic. Convert the full event to JSON mode before handing it to
            # the repository, which stores payloads with json.dumps().
            event_dict = event.model_dump(mode="json")
            self.repo.save_system_event(event_dict)
        except Exception as exc:
            logger.error("Failed to persist event %s: %s", event.event_id, exc)

    async def run(self) -> None:
        self._running = True
        await self.scanner.start()
        self.refresh_health_status()
        if AUTO_MODEL_TRAINING:
            self._tasks.append(asyncio.create_task(
                self.learning_service.run(), name="blackmarket-live-learning"
            ))
        else:
            self.learning_service.state = "disabled"
            self.learning_service.last_cycle_status = "AUTO_MODEL_TRAINING is disabled"
        async def telegram_loop():
            while self._running:
                client = self.telegram
                if client:
                    await client.poll_commands(self._handle_telegram_command)
                else:
                    await asyncio.sleep(2)
        self._tasks.append(asyncio.create_task(telegram_loop(), name="blackmarket-telegram-commands"))
        logger.info("BlackMarket AI running")
        # Main loop - keep running until stopped
        while self._running:
            await asyncio.sleep(60)
            self.disaster_recovery.watchdog.heartbeat()
            self.refresh_health_status()
            # Periodic persistence
            await self._persist_state()

    async def _persist_state(self) -> None:
        try:
            # Save open positions
            for pos in self.simulator.spot_positions.values():
                self.repo.save_position(pos)
            for pos in self.simulator.futures_positions.values():
                self.repo.save_position(pos)
            self.simulator._persist_daily_equity_baseline()
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
