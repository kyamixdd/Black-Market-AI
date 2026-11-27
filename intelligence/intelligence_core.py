"""Intelligence Core: orchestrates the complete signal generation pipeline."""
from __future__ import annotations

import logging
import time
from typing import Any

from config import SUPPORTED_TIMEFRAMES
from core.event_bus import EventBus
from intelligence.decision_engine import DecisionEngine
from intelligence.feature_engine import FeatureEngine
from intelligence.strategy_selector import StrategySelector
from learning.predictor import Predictor
from market.candle_manager import CandleManager
from market.trend_analyzer import TrendAnalyzer
from market.data_integrity import DataIntegrityGuardian
from strategies.all_strategies import (
    MeanReversionStrategy,
    ReversalStrategy,
    TrendFollowingStrategy,
)
from strategies.breakout import BreakoutStrategy
from strategies.momentum import MomentumStrategy
from core.observability import log_event

logger = logging.getLogger(__name__)


class IntelligenceCore:
    """Central coordinator for market analysis, strategy evaluation, and signal generation."""

    def __init__(self, event_bus: EventBus, candle_manager: CandleManager,
                 integrity_guardian: DataIntegrityGuardian | None = None):
        self.event_bus = event_bus
        self.candles = candle_manager
        self.integrity = integrity_guardian

        # Strategies
        self.strategies = [
            MomentumStrategy(),
            BreakoutStrategy(),
            TrendFollowingStrategy(),
            MeanReversionStrategy(),
            ReversalStrategy(),
        ]

        # Intelligence components
        self.decision_engine = DecisionEngine(event_bus)
        self.strategy_selector = StrategySelector()
        self.feature_engine = FeatureEngine()
        self.predictor = Predictor()
        self.trend_analyzer = TrendAnalyzer(candle_manager)

        # State
        self._last_signals: dict[str, list] = {}
        self._signal_ttl_seconds = 300  # 5 minutes

    def get_strategies(self) -> list:
        return self.strategies

    async def analyze_symbol(self, symbol: str, market: str) -> list[dict[str, Any]]:
        """Run all strategies on a symbol and return valid signals."""
        started = time.perf_counter()
        # Check data integrity if guardian is provided
        if self.integrity and not self.integrity.is_symbol_valid(market, symbol):
            logger.warning("Data integrity validation failed for %s %s, skipping analysis", market, symbol)
            log_event(
                logger, logging.WARNING, "signal_analysis_blocked_by_integrity",
                component="intelligence", operation="analyze_symbol",
                market=market, symbol=symbol, outcome="SKIPPED",
                recommendation="Repair or refresh invalid/stale candle data before signal generation.",
            )
            return []

        # Build multi-timeframe OHLC data
        ohlc_data = {}
        for tf in SUPPORTED_TIMEFRAMES:
            if self.candles.has_enough_data(market, symbol, tf, min_count=50):
                ohlc_data[tf] = self.candles.get_ohlc(market, symbol, tf, limit=200)

        if not ohlc_data:
            log_event(
                logger, logging.INFO, "signal_analysis_waiting_for_candles",
                component="intelligence", operation="build_multi_timeframe_features",
                market=market, symbol=symbol, outcome="SKIPPED",
                timeframe_count=0,
                recommendation="Collect at least 50 valid closed candles on one configured timeframe.",
            )
            return []

        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.analyze(symbol, market, ohlc_data)
                if signal:
                    # Add market regime — computed once per symbol, not per-strategy (I-5)
                    if not signals:
                        trend = self.trend_analyzer.get_trend_summary(market, symbol)
                    signal["regime"] = trend.get("regime", "UNKNOWN")
                    signal["data_freshness"] = "LIVE"
                    # Multi-timeframe scoring using strategy selector
                    weight = self.strategy_selector.get_weight(signal["strategy"], signal.get("regime"))
                    signal["_weight"] = weight
                    signals.append(signal)
            except Exception as exc:
                logger.error("Strategy %s failed on %s %s: %s", strategy.name, market, symbol, exc)
                log_event(
                    logger, logging.ERROR, "strategy_evaluation_failed",
                    component="intelligence", operation="evaluate_strategy",
                    market=market, symbol=symbol, outcome="FAILURE",
                    details=f"strategy={strategy.name}",
                    exception_type=type(exc).__name__,
                    recommendation="Inspect the strategy traceback and verify its OHLC/features input requirements.",
                )

        log_event(
            logger, logging.INFO, "signal_analysis_completed",
            component="intelligence", operation="analyze_symbol",
            market=market, symbol=symbol, outcome="SUCCESS",
            signal_count=len(signals), timeframe_count=len(ohlc_data),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return signals

    async def process_signals(self, signals: list[dict[str, Any]]) -> None:
        """Process signals through decision engine."""
        processed = 0
        deduplicated = 0
        for signal in signals:
            # Deduplication check
            if self._is_duplicate(signal):
                logger.debug("Signal %s deduplicated", signal["signal_id"])
                deduplicated += 1
                continue

            # Store for deduplication
            self._store_signal(signal)

            # Submit to decision engine
            await self.decision_engine.evaluate_signal(signal)
            processed += 1
        log_event(
            logger, logging.INFO, "signals_submitted_for_validation",
            component="intelligence", operation="process_signals",
            outcome="SUCCESS", signal_count=processed,
            skipped_count=deduplicated,
        )

    def _is_duplicate(self, signal: dict[str, Any]) -> bool:
        key = f"{signal['symbol']}:{signal['market']}:{signal['strategy']}:{signal['direction']}"
        recent = self._last_signals.get(key, [])
        import time
        now = time.time()
        # Filter to recent signals
        recent = [s for s in recent if now - s < self._signal_ttl_seconds]
        self._last_signals[key] = recent
        return len(recent) > 0

    def _store_signal(self, signal: dict[str, Any]) -> None:
        key = f"{signal['symbol']}:{signal['market']}:{signal['strategy']}:{signal['direction']}"
        import time
        if key not in self._last_signals:
            self._last_signals[key] = []
        self._last_signals[key].append(time.time())

    async def run_prioritized_scan(self, top_symbols: list[tuple[str, str]]) -> None:
        """Run analysis on prioritized symbols."""
        started = time.perf_counter()
        symbols_analyzed = 0
        signals_generated = 0
        failures = 0
        log_event(
            logger, logging.INFO, "prioritized_signal_scan_started",
            component="intelligence", operation="run_prioritized_scan",
            outcome="STARTED", symbols_selected=len(top_symbols),
        )
        for market, symbol in top_symbols:
            try:
                signals = await self.analyze_symbol(symbol, market)
                symbols_analyzed += 1
                signals_generated += len(signals)
                if signals:
                    await self.process_signals(signals)
            except Exception as exc:
                failures += 1
                logger.error("Analysis failed for %s %s: %s", market, symbol, exc)
                log_event(
                    logger, logging.ERROR, "symbol_signal_pipeline_failed",
                    component="intelligence", operation="run_symbol_signal_pipeline",
                    market=market, symbol=symbol, outcome="FAILURE",
                    exception_type=type(exc).__name__,
                    recommendation="Inspect the correlated symbol analysis and decision-engine traceback; other symbols continue.",
                )
        log_event(
            logger,
            logging.INFO if failures == 0 else logging.WARNING,
            "prioritized_signal_scan_completed",
            component="intelligence", operation="run_prioritized_scan",
            outcome="SUCCESS" if failures == 0 else "PARTIAL_FAILURE",
            symbols_selected=len(top_symbols),
            eligible_count=symbols_analyzed,
            signal_count=signals_generated,
            failed_count=failures,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            recommendation=None if failures == 0 else "Review symbol_signal_pipeline_failed entries; scanning continued for remaining symbols.",
        )