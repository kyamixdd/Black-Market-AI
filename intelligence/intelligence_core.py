"""Intelligence Core: orchestrates the complete signal generation pipeline."""
from __future__ import annotations

import logging
from typing import Any

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
        # Check data integrity if guardian is provided
        if self.integrity and not self.integrity.is_symbol_valid(market, symbol):
            logger.warning("Data integrity validation failed for %s %s, skipping analysis", market, symbol)
            return []

        # Build multi-timeframe OHLC data
        ohlc_data = {}
        for tf in ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]:
            if self.candles.has_enough_data(market, symbol, tf, min_count=50):
                ohlc_data[tf] = self.candles.get_ohlc(market, symbol, tf, limit=200)

        if not ohlc_data:
            return []

        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.analyze(symbol, market, ohlc_data)
                if signal:
                    # Add market regime
                    trend = self.trend_analyzer.get_trend_summary(market, symbol)
                    signal["regime"] = trend.get("regime", "UNKNOWN")
                    # Freshness is derived from the timestamps of the candles
                    # actually used, not asserted unconditionally as LIVE.
                    newest_close_ms = 0
                    newest_tf_seconds = 60
                    for timeframe in ohlc_data:
                        candles = self.candles.get_series(market, symbol, timeframe, limit=1)
                        if candles:
                            close_ms = int(candles[-1].get("close_time", candles[-1]["open_time"]))
                            if close_ms > newest_close_ms:
                                newest_close_ms = close_ms
                                from market.candle_manager import TIMEFRAME_SECONDS
                                newest_tf_seconds = TIMEFRAME_SECONDS.get(timeframe, 60)
                    age_seconds = max(0.0, time.time() - newest_close_ms / 1000) if newest_close_ms else None
                    freshness_limit = max(90.0, newest_tf_seconds * 2.0)
                    signal["data_age_seconds"] = age_seconds
                    signal["data_freshness"] = (
                        "LIVE" if age_seconds is not None and age_seconds <= freshness_limit else "STALE"
                    )
                    # Multi-timeframe scoring using strategy selector
                    weight = self.strategy_selector.get_weight(signal["strategy"], signal.get("regime"))
                    signal["_weight"] = weight
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

            # Submit to decision engine
            await self.decision_engine.evaluate_signal(signal)

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