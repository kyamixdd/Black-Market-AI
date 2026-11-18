"""Intelligence Core: orchestrates the complete signal generation pipeline."""
from __future__ import annotations

import logging
from typing import Any

from config import LEARNING_MODE, ML_ENABLED, SIGNAL_DEDUP_WINDOW_SECONDS, TIMEFRAMES
from core.event_bus import EventBus
from core.event_models import EventType, make_event
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
        self._signal_ttl_seconds = SIGNAL_DEDUP_WINDOW_SECONDS

    def get_strategies(self) -> list:
        return self.strategies

    async def analyze_symbol(self, symbol: str, market: str) -> list[dict[str, Any]]:
        """Run all strategies on a symbol and return valid signals."""
        # Check data integrity if guardian is provided
        if self.integrity and not self.integrity.is_symbol_valid(market, symbol):
            logger.warning("Data integrity validation failed for %s %s, skipping analysis", market, symbol)
            return []

        # Build multi-timeframe OHLC data
        ohlc_data = {}
        for tf in TIMEFRAMES:
            if self.candles.has_enough_data(market, symbol, tf, min_count=50):
                ohlc_data[tf] = self.candles.get_ohlc(market, symbol, tf, limit=200)

        if not ohlc_data:
            return []

        # Build one shared ML prediction for the symbol and current market state.
        ml_prediction = None
        if ML_ENABLED and LEARNING_MODE in {"hybrid", "ml_only"} and self.predictor.is_trained:
            try:
                features = self.feature_engine.build_features(symbol, market, ohlc_data)
                if features.size and np.isfinite(features).all():
                    ml_prediction = self.predictor.predict(features)
            except Exception:
                logger.exception("ML inference failed for %s %s", market, symbol)
                if LEARNING_MODE == "ml_only":
                    return []

        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.analyze(symbol, market, ohlc_data)
                if signal:
                    trend = self.trend_analyzer.get_trend_summary(market, symbol)
                    signal["regime"] = trend.get("regime", "UNKNOWN")
                    signal["data_freshness"] = "LIVE"
                    signal["_weight"] = self.strategy_selector.get_weight(
                        signal["strategy"], signal.get("regime")
                    )

                    if LEARNING_MODE == "ml_only":
                        if ml_prediction is None:
                            continue
                        is_long = signal["direction"] in ("LONG", "BUY")
                        directional_probability = (
                            ml_prediction["prob_up"] if is_long else ml_prediction["prob_down"]
                        )
                        if directional_probability < 0.45:
                            continue
                        signal["raw_score"] = min(100.0, directional_probability * 100.0)
                    elif LEARNING_MODE == "hybrid" and ml_prediction is not None:
                        is_long = signal["direction"] in ("LONG", "BUY")
                        directional_probability = (
                            ml_prediction["prob_up"] if is_long else ml_prediction["prob_down"]
                        )
                        rule_score = max(0.0, min(1.0, float(signal.get("raw_score", 50.0)) / 100.0))
                        signal["raw_score"] = (
                            0.70 * rule_score + 0.30 * directional_probability
                        ) * 100.0

                    if ml_prediction is not None:
                        signal["ml_predicted_class"] = ml_prediction["predicted_class"]
                        signal["ml_confidence"] = ml_prediction["confidence"]
                        signal["ml_prob_up"] = ml_prediction["prob_up"]
                        signal["ml_prob_down"] = ml_prediction["prob_down"]
                    signals.append(signal)
            except Exception as exc:
                logger.error("Strategy %s failed on %s %s: %s", strategy.name, market, symbol, exc)

        return signals

    async def process_signals(self, signals: list[dict[str, Any]]) -> None:
        """Process signals through decision engine."""
        for signal in signals:
            # Deduplication check
            if self._is_duplicate(signal):
                logger.debug("Signal %s deduplicated", signal["signal_id"])
                continue

            # Store for deduplication
            self._store_signal(signal)

            # Publish the proposal so the orchestrator's single event pipeline
            # can persist it and make the validated/rejected decision.
            await self.event_bus.publish(make_event(
                EventType.SIGNAL_PROPOSED,
                "intelligence",
                symbol=signal["symbol"],
                market=signal["market"],
                **{k: v for k, v in signal.items() if k not in {"symbol", "market"}},
            ))

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
        for market, symbol in top_symbols:
            try:
                signals = await self.analyze_symbol(symbol, market)
                if signals:
                    await self.process_signals(signals)
            except Exception as exc:
                logger.error("Analysis failed for %s %s: %s", market, symbol, exc)